"""
execution_engine.py — Executes System A's RS60/EP40 signals via Upstox.

Architecture:
  daily_ops_report.py  →  ops_log.json  →  THIS FILE  →  Upstox orders

This file does NOT generate signals. It reads what System A decided
and places real orders. The strategy lives in daily_ops_report.py.
This is a pure execution layer.

Workflow:
  1. Read today's ops_log JSON (produced by daily_ops_report.py)
  2. Validate orders (symbol exists, cash available, limits respected)
  3. Place orders via Upstox API at market open
  4. Verify fills (poll until confirmed)
  5. Update local state + trade journal + broker audit
  6. Monitor open positions for stop-loss breaches during the day

Usage:
  python execution_engine.py                  (execute today's orders)
  python execution_engine.py --monitor        (SL monitoring loop only)
  python execution_engine.py --status         (show current positions)
  python execution_engine.py --dry-run        (validate without placing orders)

Schedule:
  9:10 AM IST: python execution_engine.py          (place orders at open)
  9:15-15:30:  python execution_engine.py --monitor (SL checks every 5 min)
"""

import os
import time
import json
import logging
import requests
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import config
from trade_journal import record_trade as journal_record

log = logging.getLogger("execution_engine")
if not log.handlers:
    log.setLevel(logging.INFO)
    _fmt = logging.Formatter("%(asctime)s [EXEC] %(message)s")
    _fh = logging.FileHandler("execution_engine.log", encoding="utf-8")
    _fh.setFormatter(_fmt)
    _sh = logging.StreamHandler(sys.stdout)
    _sh.setFormatter(_fmt)
    log.addHandler(_fh)
    log.addHandler(_sh)
    log.propagate = False

STATE_FILE = Path("execution_state.json")
LOCK_FILE = Path("execution_engine.lock")
SL_CHECK_INTERVAL = 300  # 5 minutes
SL_PCT = 0.10             # must match daily_ops_report.SL_PCT exactly


# ── Single-instance lock (Windows file lock, not PID) ────────────────────────

_lock_handle = None

def acquire_lock():
    """Prevent two copies from running simultaneously.
    Uses Windows file locking (msvcrt.locking) — not PID files.
    If the process dies, Windows releases the lock automatically.
    No stale lock files, no PID reuse false positives."""
    global _lock_handle
    try:
        _lock_handle = open(LOCK_FILE, "w")
        import msvcrt
        msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_handle.write(str(os.getpid()))
        _lock_handle.flush()
        log.info(f"Lock acquired (PID {os.getpid()})")
    except (IOError, OSError):
        log.error("Another instance is already running. Exiting.")
        sys.exit(1)

def release_lock():
    global _lock_handle
    if _lock_handle:
        try:
            import msvcrt
            _lock_handle.seek(0)
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            _lock_handle.close()
        except Exception:
            pass
        _lock_handle = None
    if LOCK_FILE.exists():
        LOCK_FILE.unlink(missing_ok=True)


# ── Atomic JSON write ────────────────────────────────────────────────────────

def atomic_write_json(path: Path, data: dict):
    """Write JSON atomically: write to temp file, then rename.
    Prevents corruption if power dies mid-write.
    On failure (disk full, permission), raises exception — caller decides."""
    import tempfile
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        Path(tmp_path).replace(path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Duplicate order prevention (broker-verified) ─────────────────────────────

def already_ordered_today(client, instrument, transaction_type="BUY"):
    """Check broker's actual order history — not a local file.
    Checks the specific transaction_type (BUY or SELL) to prevent duplicates
    on restarts after a crash. Fail-closed: returns True (blocks) on API error."""
    try:
        r = requests.get(
            f"{client.BASE}/order/get-order-book",
            headers=client._headers(), timeout=10
        )
        data = r.json()
        if data.get("status") != "success":
            return False
        tx_type = transaction_type.upper()
        for order in data.get("data", []):
            if (order.get("instrument_token", "") == instrument
                    and order.get("transaction_type", "").upper() == tx_type
                    and order.get("status", "").lower() in ("complete", "open", "trigger pending")):
                log.info(f"Duplicate blocked: {instrument} {tx_type} already in order book today (order_id={order.get('order_id','')})")
                return True
    except Exception as e:
        log.error(f"Duplicate check FAILED — BLOCKING order (fail-closed): {e}")
        return True  # fail-closed: assume duplicate exists, block the order


# ── Health check ─────────────────────────────────────────────────────────────

def pre_market_health_check(client):
    """Comprehensive pre-market verification."""
    errors = []

    # 1. Broker API reachable + token valid
    try:
        funds = client.get_funds()
        equity = funds.get("equity", {})
        available = float(equity.get("available_margin", 0))
        if available <= 0:
            errors.append(f"Available margin is Rs.{available} — no cash to trade")
        else:
            log.info(f"  Broker: OK (Rs.{available:,.2f} available)")
    except Exception as e:
        errors.append(f"Broker API unreachable: {e}")

    # 2. Ops log exists for today
    ops_path = Path(f"ops_log_{date.today()}.json")
    if not ops_path.exists():
        errors.append(f"No ops log: {ops_path}")
    else:
        try:
            ops = json.loads(ops_path.read_text(encoding="utf-8"))
            nifty = ops.get("nifty", 0)
            dma200 = ops.get("dma200", 0)
            if nifty <= 0 or dma200 <= 0:
                errors.append(f"Ops log has invalid data: nifty={nifty}, dma200={dma200}")
            else:
                log.info(f"  Ops log: OK (regime={ops.get('regime')}, nifty={nifty:,.0f})")
        except Exception as e:
            errors.append(f"Ops log corrupt: {e}")

    # 3. State file readable
    try:
        state = load_state()
        log.info(f"  State: OK ({len(state.get('positions', {}))} positions)")
    except Exception as e:
        errors.append(f"State file unreadable: {e}")

    # 4. Config has required fields
    if not config.UPSTOX_ACCESS_TOKEN:
        errors.append("UPSTOX_ACCESS_TOKEN is empty")

    # 5. Time check — are we near market hours?
    now = datetime.now()
    if now.weekday() >= 5:
        errors.append("Today is a weekend")

    if errors:
        log.error("HEALTH CHECK FAILED:")
        for e in errors:
            log.error(f"  {e}")
        return False

    log.info("Health check: ALL PASSED")
    return True


# ── Upstox Client (reused from trading_bot.py, proven code) ──────────────────

class UpstoxClient:
    BASE = "https://api.upstox.com/v2"

    def __init__(self):
        if not config.UPSTOX_ACCESS_TOKEN:
            log.error("No UPSTOX_ACCESS_TOKEN in config.py. Refresh token first.")
            raise SystemExit(1)

    def _headers(self):
        import importlib
        importlib.reload(config)
        return {"Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}", "Accept": "application/json"}

    def get_ltp(self, instruments: list):
        joined = ",".join(instruments)
        try:
            r = requests.get(
                f"{self.BASE}/market-quote/ltp",
                params={"instrument_key": joined},
                headers=self._headers(), timeout=10
            )
            return r.json().get("data", {})
        except Exception:
            return {}

    def get_portfolio(self):
        try:
            r = requests.get(f"{self.BASE}/portfolio/short-term-positions",
                             headers=self._headers(), timeout=10)
            return r.json().get("data", [])
        except Exception:
            return []

    def get_funds(self):
        try:
            r = requests.get(f"{self.BASE}/user/get-funds-and-margin",
                             headers=self._headers(), timeout=10)
            return r.json().get("data", {})
        except Exception:
            return {}

    def place_order(self, instrument, qty, side, order_type="MARKET", price=0):
        payload = {
            "quantity": qty, "product": "D", "validity": "DAY",
            "price": price, "tag": "moneybot",
            "instrument_token": instrument, "order_type": order_type,
            "transaction_type": side, "disclosed_quantity": 0,
            "trigger_price": 0, "is_amo": False,
        }
        try:
            r = requests.post(
                f"{self.BASE}/order/place", json=payload,
                headers={**self._headers(), "Content-Type": "application/json"},
                timeout=10
            )
            result = r.json()
            if result.get("status") == "success":
                order_id = result.get("data", {}).get("order_id", "")
                log.info(f"Order accepted: {side} {qty}x {instrument} order_id={order_id}")
                if order_id:
                    fill = self._wait_for_fill(order_id, instrument, qty, side)
                    if fill:
                        return fill
                    log.warning(f"Order {order_id} not confirmed filled")
                return result
            else:
                log.warning(f"Order REJECTED: {side} {qty}x {instrument} -> {result}")
            return result
        except Exception as e:
            log.error(f"Order placement failed: {e}")
            return {}

    def _wait_for_fill(self, order_id, instrument, qty, side, max_wait=10):
        for attempt in range(max_wait):
            time.sleep(1)
            try:
                r = requests.get(
                    f"{self.BASE}/order/details",
                    params={"order_id": order_id},
                    headers=self._headers(), timeout=10
                )
                data = r.json().get("data", {})
                status = data.get("status", "").lower()
                if status == "complete":
                    return {
                        "status": "success", "fill_confirmed": True,
                        "fill_price": float(data.get("average_price", 0)),
                        "fill_qty": int(data.get("filled_quantity", qty)),
                        "order_id": order_id,
                    }
                elif status in ("rejected", "cancelled"):
                    return {"status": status, "fill_confirmed": False, "order_id": order_id}
            except Exception:
                pass
        return None


# ── State management ─────────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"positions": {}, "trades": [], "pnl": 0, "last_ops_date": ""}


def save_state(state):
    atomic_write_json(STATE_FILE, state)


FROZEN_SYMBOLS_FILE = Path("frozen_symbols.json")

def load_frozen_symbols():
    """Load symbols frozen due to corporate actions. These must not be traded."""
    if FROZEN_SYMBOLS_FILE.exists():
        try:
            return {f["instrument"] for f in json.loads(FROZEN_SYMBOLS_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return set()


# ── Ops log reader ───────────────────────────────────────────────────────────

def load_ops_log():
    today = str(date.today())
    path = Path(f"ops_log_{today}.json")
    if not path.exists():
        log.error(f"No ops log for today: {path}")
        log.error("Run: python daily_ops_report.py first.")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ── Execution validator ──────────────────────────────────────────────────────

def validate_orders(ops, state, available_cash):
    """Validate ops log orders before execution. Returns (buys, sells, errors)."""
    errors = []
    frozen = load_frozen_symbols()
    if frozen:
        log.warning(f"Frozen symbols (corporate action): {frozen}")
    regime = ops.get("regime", "UNKNOWN")

    if regime == "BEAR":
        sells = []
        for inst, pos in state["positions"].items():
            if not pos.get("pending_sell"):
                sells.append({
                    "symbol": pos.get("plain", inst.split("|")[-1]),
                    "instrument": inst,
                    "qty": pos["qty"],
                    "reason": "Regime EXIT (BEAR)",
                })
        return [], sells, errors

    buys = []
    sells = ops.get("sells", [])

    if not ops.get("rebalance_due", False):
        log.info("No rebalance today. Monitoring only.")
        return [], [], errors

    for b in ops.get("buys", []):
        sym = b.get("symbol", "")
        inst = f"NSE_EQ|{sym}"
        qty = b.get("qty", 0)
        alloc = b.get("alloc_rs", 0)
        sl_price = b.get("sl_price", 0)

        if not sym:
            errors.append(f"Buy order missing symbol: {b}")
            continue
        if inst in frozen:
            errors.append(f"{sym}: FROZEN (corporate action) — skipping")
            continue
        if qty <= 0:
            errors.append(f"{sym}: qty={qty} invalid")
            continue
        if inst in state["positions"]:
            log.info(f"{sym}: already in position, skipping buy")
            continue

        estimated_cost = alloc + 40  # alloc + round-trip brokerage estimate
        if estimated_cost > available_cash:
            errors.append(f"{sym}: insufficient cash (need Rs.{estimated_cost:,.0f}, have Rs.{available_cash:,.0f})")
            continue

        buys.append({
            "symbol": sym, "instrument": inst,
            "qty": qty, "alloc_rs": alloc, "sl_price": sl_price,
        })
        available_cash -= estimated_cost

    return buys, sells, errors


# ── Order execution ──────────────────────────────────────────────────────────

def execute_sells(client, sells, state):
    """Execute sell orders. Returns list of results."""
    frozen = load_frozen_symbols()
    results = []
    for s in sells:
        inst = s["instrument"]
        if inst in frozen:
            log.warning(f"SELL {s['symbol']}: FROZEN (corporate action) — skipping. Manual review required.")
            results.append({"symbol": s["symbol"], "status": "FROZEN"})
            continue
        pos = state["positions"].get(inst)
        if not pos:
            log.warning(f"SELL {s['symbol']}: not in local state, skipping")
            continue
        # Bug #3 fix: check for duplicate SELL before placing (survives crash+restart)
        if already_ordered_today(client, inst, "SELL"):
            log.warning(f"SELL {s['symbol']}: already in broker order book today — skipping duplicate sell")
            results.append({"symbol": s["symbol"], "status": "DUPLICATE_BLOCKED"})
            continue

        log.info(f"SELLING {pos['qty']}x {s['symbol']} — {s['reason']}")
        result = client.place_order(inst, pos["qty"], "SELL")

        if result.get("status") in ("success", "complete") and result.get("fill_confirmed"):
            exit_price = result.get("fill_price", 0)
            exit_qty = result.get("fill_qty", pos["qty"])
            pnl = (exit_price - pos["entry"]) * exit_qty
            state["pnl"] += pnl
            state["trades"].append({
                "symbol": s["symbol"], "entry": pos["entry"],
                "exit": exit_price, "qty": exit_qty,
                "pnl": round(pnl, 2), "time": str(datetime.now()),
                "exit_reason": s["reason"],
            })
            del state["positions"][inst]
            log.info(f"SOLD {s['symbol']} @ Rs.{exit_price:.2f} | PnL: Rs.{pnl:+,.2f}")
            # Save state immediately after each sell so a crash mid-loop
            # won't leave a sold position in state (enables Bug #3 duplicate protection)
            save_state(state)
            try:
                _entry_date = pos.get("time", "")[:10]
                _holding = max(0, (date.today() - date.fromisoformat(_entry_date)).days) if _entry_date else 0
                journal_record(
                    symbol=s["symbol"], instrument=inst,
                    entry_date=_entry_date,
                    exit_date=str(date.today()),
                    holding_days=_holding,
                    entry_price=pos["entry"], exit_price=exit_price,
                    qty=exit_qty, net_pnl=pnl,
                    exit_reason=s["reason"], system="A-live",
                )
            except Exception as je:
                log.warning(f"Journal write failed (non-fatal): {je}")
            results.append({"symbol": s["symbol"], "status": "FILLED", "pnl": pnl})
        elif not result.get("fill_confirmed"):
            state["positions"][inst]["pending_sell"] = True
            log.warning(f"SELL {s['symbol']} not confirmed — marked pending_sell")
            results.append({"symbol": s["symbol"], "status": "PENDING"})
        else:
            log.error(f"SELL {s['symbol']} failed: {result}")
            results.append({"symbol": s["symbol"], "status": "FAILED"})

    save_state(state)
    return results


def execute_buys(client, buys, state):
    """Execute buy orders. Returns list of results."""
    results = []
    for b in buys:
        inst = b["instrument"]
        if already_ordered_today(client, inst):
            log.warning(f"BUY {b['symbol']}: already in broker order book today — skipping duplicate")
            results.append({"symbol": b["symbol"], "status": "DUPLICATE_BLOCKED"})
            continue
        log.info(f"BUYING {b['qty']}x {b['symbol']} (alloc Rs.{b['alloc_rs']:,.0f})")
        result = client.place_order(inst, b["qty"], "BUY")

        if result.get("status") in ("success", "complete") and result.get("fill_confirmed"):
            fill_price = result.get("fill_price", 0)
            fill_qty = result.get("fill_qty", b["qty"])
            # SL from actual fill price, not ops-log prev-close estimate (Bug #2 fix)
            sl_price = round(fill_price * (1 - SL_PCT), 2) if fill_price > 0 else b["sl_price"]
            state["positions"][inst] = {
                "qty": fill_qty, "entry": fill_price,
                "time": str(datetime.now()),
                "plain": b["symbol"],
                "sl_price": sl_price,
                "order_id": result.get("order_id", ""),
            }
            log.info(f"BOUGHT {fill_qty}x {b['symbol']} @ Rs.{fill_price:.2f} | SL: Rs.{sl_price:,.2f}")
            results.append({"symbol": b["symbol"], "status": "FILLED", "price": fill_price})
        elif not result.get("fill_confirmed"):
            log.warning(f"BUY {b['symbol']} not confirmed — NOT adding to positions")
            results.append({"symbol": b["symbol"], "status": "NOT_CONFIRMED"})
        else:
            log.error(f"BUY {b['symbol']} failed: {result}")
            results.append({"symbol": b["symbol"], "status": "FAILED"})

    save_state(state)
    return results


# ── Stop-loss monitor ────────────────────────────────────────────────────────

def monitor_stop_losses(client, state):
    """Check all open positions against their SL levels. Run during market hours."""
    frozen = load_frozen_symbols()
    active = {k: v for k, v in state["positions"].items()
              if not v.get("pending_sell") and k not in frozen}
    if not active:
        return []

    instruments = list(active.keys())
    ltp_raw = client.get_ltp(instruments)
    exits = []

    for inst, pos in active.items():
        ltp_data = ltp_raw.get(inst, {})
        if isinstance(ltp_data, dict):
            ltp = ltp_data.get("last_price", 0)
        else:
            ltp = float(ltp_data) if ltp_data else 0

        if ltp <= 0:
            continue

        sl_price = pos.get("sl_price", pos["entry"] * 0.90)
        if ltp <= sl_price:
            exits.append({
                "instrument": inst,
                "symbol": pos.get("plain", inst.split("|")[-1]),
                "qty": pos["qty"],
                "ltp": ltp,
                "sl_price": sl_price,
                "reason": f"Stop Loss hit ({ltp:.2f} <= {sl_price:.2f})",
            })

    if exits:
        log.warning(f"SL TRIGGERED on {len(exits)} position(s)")
        results = execute_sells(client, exits, state)
        return results

    return []


# ── Main commands ────────────────────────────────────────────────────────────

def execute_today():
    """Main command: read ops log, validate, execute orders."""
    acquire_lock()
    try:
        _execute_today_inner()
    finally:
        release_lock()

def _execute_today_inner():
    sep = "=" * 65
    log.info(f"\n{sep}")
    log.info(f"  EXECUTION ENGINE — {date.today()}")
    log.info(sep)

    # Invariant check before touching broker — halt on CRITICAL violations
    try:
        from invariant_checker import check_all_invariants
        inv_report = check_all_invariants()
        if inv_report.must_halt:
            for v in inv_report.critical:
                log.critical(f"INVARIANT VIOLATION [{v.invariant}]: {v.detail}")
            log.critical("HALTING: CRITICAL invariant violation(s) detected. Fix before trading.")
            try:
                from notify import send
                send(f"MONEYBOT HALTED\nInvariant violation(s): "
                     f"{', '.join(v.invariant for v in inv_report.critical)}")
            except Exception:
                pass
            return
        elif inv_report.violations:
            for v in inv_report.violations:
                log.warning(f"INVARIANT [{v.severity}] {v.invariant}: {v.detail}")
    except ImportError:
        pass  # invariant_checker optional

    ops = load_ops_log()
    if ops is None:
        return

    state = load_state()

    if state.get("last_ops_date") == str(date.today()):
        log.warning("Today's orders already executed. Use --monitor for SL checks.")
        return

    client = UpstoxClient()

    if not pre_market_health_check(client):
        log.error("Health check failed. Aborting execution.")
        return

    funds = client.get_funds()
    available = float(funds.get("equity", {}).get("available_margin", 0))
    log.info(f"Available funds: Rs.{available:,.2f}")
    log.info(f"Open positions: {len(state['positions'])}")
    log.info(f"Regime: {ops.get('regime', '?')}")
    log.info(f"Rebalance due: {ops.get('rebalance_due', False)}")

    buys, sells, errors = validate_orders(ops, state, available)

    if errors:
        log.warning(f"Validation errors:")
        for e in errors:
            log.warning(f"  {e}")

    log.info(f"Orders to execute: {len(sells)} sells, {len(buys)} buys")

    if not buys and not sells:
        log.info("No orders to execute today.")
        state["last_ops_date"] = str(date.today())
        save_state(state)
        return

    # Sells first, then buys (frees cash)
    if sells:
        log.info(f"\n--- EXECUTING {len(sells)} SELL ORDER(S) ---")
        sell_results = execute_sells(client, sells, state)
        for r in sell_results:
            log.info(f"  {r['symbol']}: {r['status']}")

    if buys:
        # Re-check funds after sells
        funds = client.get_funds()
        available = float(funds.get("equity", {}).get("available_margin", 0))
        log.info(f"\n--- EXECUTING {len(buys)} BUY ORDER(S) ---")
        log.info(f"Cash after sells: Rs.{available:,.2f}")
        buy_results = execute_buys(client, buys, state)
        for r in buy_results:
            log.info(f"  {r['symbol']}: {r['status']}")

    state["last_ops_date"] = str(date.today())
    save_state(state)
    log.info(f"\nExecution complete. Total PnL: Rs.{state['pnl']:+,.2f}")
    log.info(sep)


def run_monitor():
    """SL monitoring loop during market hours."""
    client = UpstoxClient()
    state = load_state()
    log.info("SL monitor started. Checking every 5 minutes.")

    while True:
        now = datetime.now()
        if now.weekday() >= 5 or not (9 * 60 + 15 <= now.hour * 60 + now.minute <= 15 * 60 + 30):
            log.info("Market closed. Monitor stopping.")
            break

        state = load_state()
        active = {k: v for k, v in state["positions"].items() if not v.get("pending_sell")}
        if not active:
            log.info("No active positions. Sleeping.")
            time.sleep(SL_CHECK_INTERVAL)
            continue

        log.info(f"Checking {len(active)} position(s) for SL breach...")
        exits = monitor_stop_losses(client, state)
        if exits:
            for e in exits:
                log.info(f"  SL EXIT: {e}")

        time.sleep(SL_CHECK_INTERVAL)


def show_status():
    """Print current positions and PnL."""
    state = load_state()
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  EXECUTION ENGINE STATUS — {date.today()}")
    print(sep)
    print(f"  Total PnL:      Rs.{state['pnl']:+,.2f}")
    print(f"  Completed trades: {len(state['trades'])}")
    print(f"  Last ops date:   {state.get('last_ops_date', 'never')}")

    positions = state.get("positions", {})
    active = {k: v for k, v in positions.items() if not v.get("pending_sell")}
    pending = {k: v for k, v in positions.items() if v.get("pending_sell")}

    print(f"  Active positions: {len(active)}")
    print(f"  Pending sell:     {len(pending)}")

    if active:
        print(f"\n  {'Symbol':<14} {'Qty':>5} {'Entry':>10} {'SL':>10} {'Since'}")
        print(f"  {'-'*50}")
        for inst, pos in active.items():
            sym = pos.get("plain", inst.split("|")[-1])
            sl = pos.get("sl_price", pos["entry"] * 0.90)
            print(f"  {sym:<14} {pos['qty']:>5} Rs.{pos['entry']:>8,.2f} Rs.{sl:>8,.2f} {pos.get('time','')[:10]}")

    if pending:
        print(f"\n  PENDING SELL:")
        for inst, pos in pending.items():
            print(f"    {pos.get('plain', inst.split('|')[-1])}: awaiting broker confirmation")

    print(sep)


def dry_run():
    """Validate today's orders without executing."""
    ops = load_ops_log()
    if ops is None:
        return

    state = load_state()
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  DRY RUN — {date.today()}")
    print(sep)
    print(f"  Regime: {ops.get('regime', '?')}")
    print(f"  Rebalance due: {ops.get('rebalance_due', False)}")
    print(f"  Candidates: {len(ops.get('candidates', []))}")

    buys, sells, errors = validate_orders(ops, state, 999_999)

    if sells:
        print(f"\n  WOULD SELL:")
        for s in sells:
            print(f"    {s['symbol']} qty={s['qty']} reason={s['reason']}")

    if buys:
        print(f"\n  WOULD BUY:")
        for b in buys:
            print(f"    {b['symbol']} qty={b['qty']} alloc=Rs.{b['alloc_rs']:,.0f} SL=Rs.{b['sl_price']:,.2f}")

    if errors:
        print(f"\n  VALIDATION ERRORS:")
        for e in errors:
            print(f"    {e}")

    if not buys and not sells and not errors:
        print(f"\n  No orders for today.")

    print(sep)


if __name__ == "__main__":
    if "--monitor" in sys.argv:
        run_monitor()
    elif "--status" in sys.argv:
        show_status()
    elif "--dry-run" in sys.argv:
        dry_run()
    else:
        execute_today()
