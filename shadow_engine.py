"""
shadow_engine.py — Shadow Strategy Engine (experimental, read-only from broker).

Runs alongside the production RS60/EP40 strategy. Uses the SAME market data
and candidate list already computed by daily_ops_report.py. Makes completely
independent trading decisions based on a 50-DMA regime filter instead of the
production 200-DMA filter.

CRITICAL CONSTRAINTS:
  - NEVER calls the broker API to place orders.
  - NEVER reads or writes production state files.
  - All state is isolated in shadow_state.json and shadow_journal.csv.
  - Results are for evaluation only. Human approval required before any
    experimental strategy is allowed to trade real money.

Shadow strategy vs Production strategy:
  Production (v1): Regime = Nifty > 200-DMA (Policy C, conservative)
  Shadow    (v2): Regime = Nifty > 50-DMA  (faster entry, higher turnover)

Same in both: RS60/EP40 scoring, Top-10 candidates, SL=10%, rebalance every 10d
"""

import json
import os
import csv
import tempfile
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

log = logging.getLogger("shadow_engine")
if not log.handlers:
    log.setLevel(logging.INFO)
    _fmt = logging.Formatter("%(asctime)s [SHADOW] %(message)s")
    _fh = logging.FileHandler("shadow_engine.log", encoding="utf-8")
    _fh.setFormatter(_fmt)
    _sh = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    log.addHandler(_fh)
    log.addHandler(_sh)
    log.propagate = False

SHADOW_STATE_FILE   = Path("shadow_state.json")
SHADOW_JOURNAL_FILE = Path("shadow_journal.csv")

try:
    import config as _cfg
    SHADOW_CAPITAL = getattr(_cfg, "TRADING_CAPITAL_INR", 5_000)
except Exception:
    SHADOW_CAPITAL = 5_000

PER_POS  = SHADOW_CAPITAL // 10   # same allocation per position as production
SL_PCT   = 0.10                   # same 10% stop-loss


# ── Journal fields (mirrors trade_journal.py) ────────────────────────────────
JOURNAL_FIELDS = [
    "trade_id", "entry_date", "exit_date", "holding_days",
    "symbol", "entry_price", "exit_price", "qty",
    "gross_pnl", "net_pnl", "return_pct",
    "exit_reason", "regime_at_entry", "regime_at_exit",
]


def _ensure_journal_header():
    if not SHADOW_JOURNAL_FILE.exists():
        with open(SHADOW_JOURNAL_FILE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=JOURNAL_FIELDS).writeheader()


def _next_journal_id():
    if not SHADOW_JOURNAL_FILE.exists():
        return 1
    with open(SHADOW_JOURNAL_FILE, "r", encoding="utf-8") as f:
        return max(1, sum(1 for _ in f) - 1)


def _record_trade(symbol, entry_date, exit_date, entry_price,
                  exit_price, qty, exit_reason, regime_at_entry, regime_at_exit):
    _ensure_journal_header()
    try:
        holding = max(0, (date.fromisoformat(exit_date) - date.fromisoformat(entry_date)).days)
    except Exception:
        holding = 0
    gross_pnl  = (exit_price - entry_price) * qty
    net_pnl    = gross_pnl  # shadow: no brokerage (to isolate strategy effect)
    return_pct = round(net_pnl / (entry_price * qty) * 100, 4) if entry_price and qty else 0

    row = {
        "trade_id":       _next_journal_id(),
        "entry_date":     entry_date,
        "exit_date":      exit_date,
        "holding_days":   holding,
        "symbol":         symbol,
        "entry_price":    round(entry_price, 2),
        "exit_price":     round(exit_price, 2),
        "qty":            qty,
        "gross_pnl":      round(gross_pnl, 2),
        "net_pnl":        round(net_pnl, 2),
        "return_pct":     return_pct,
        "exit_reason":    exit_reason,
        "regime_at_entry": regime_at_entry,
        "regime_at_exit":  regime_at_exit,
    }
    with open(SHADOW_JOURNAL_FILE, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=JOURNAL_FIELDS).writerow(row)
    return row


# ── State management ─────────────────────────────────────────────────────────

def _load_state():
    if SHADOW_STATE_FILE.exists():
        try:
            return json.loads(SHADOW_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "cash":       float(SHADOW_CAPITAL),
        "positions":  {},   # symbol -> {entry, qty, entry_date, sl_price, regime_at_entry}
        "trades":     [],
        "pnl":        0.0,
        "last_run":   "",
    }


def _save_state(state):
    fd, tmp = tempfile.mkstemp(dir=SHADOW_STATE_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
        Path(tmp).replace(SHADOW_STATE_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Shadow regime decision ────────────────────────────────────────────────────

def _shadow_regime(ops: dict) -> str:
    """
    Shadow uses 50-DMA as regime filter (production uses 200-DMA).
    Nifty > 50-DMA  -> ACTIVE (enter trades)
    Nifty <= 50-DMA -> CASH   (hold cash)
    """
    nifty = ops.get("nifty", 0)
    dma50 = ops.get("dma50", 0)
    if nifty <= 0 or dma50 <= 0:
        return "CASH"
    return "ACTIVE" if nifty > dma50 else "CASH"


# ── Main daily runner ─────────────────────────────────────────────────────────

def run_shadow_daily(ops: dict) -> dict:
    """
    Run one day of the shadow strategy.
    ops: the ops_log dict produced by daily_ops_report.py (already loaded).
    Returns a summary dict for the daily comparison report.
    """
    today      = str(date.today())
    state      = _load_state()
    s_regime   = _shadow_regime(ops)
    prod_regime = ops.get("regime", "UNKNOWN")
    candidates  = ops.get("candidates", [])
    rebal_due   = ops.get("rebalance_due", False)

    log.info(f"Shadow run: prod_regime={prod_regime} shadow_regime={s_regime} "
             f"candidates={len(candidates)} rebal={rebal_due}")

    exits   = []
    entries = []

    # ── Step 1: Exit positions if shadow goes CASH ────────────────────────────
    if s_regime == "CASH" and state["positions"]:
        log.info(f"Shadow regime = CASH — simulating exit of {len(state['positions'])} position(s)")
        # Use today's candidate prices as proxy for exit price; fall back to entry
        price_map = {c["symbol"]: c["price"] for c in candidates}
        for sym, pos in list(state["positions"].items()):
            exit_price = price_map.get(sym, pos["entry"])
            pnl = (exit_price - pos["entry"]) * pos["qty"]
            state["cash"] += exit_price * pos["qty"]
            state["pnl"]  += pnl
            state["trades"].append({
                "symbol": sym, "entry": pos["entry"], "exit": exit_price,
                "qty": pos["qty"], "pnl": round(pnl, 2),
                "time": today, "exit_reason": "Regime EXIT (CASH)",
            })
            _record_trade(
                symbol=sym,
                entry_date=pos.get("entry_date", today),
                exit_date=today,
                entry_price=pos["entry"],
                exit_price=exit_price,
                qty=pos["qty"],
                exit_reason="Regime EXIT (Shadow CASH)",
                regime_at_entry=pos.get("regime_at_entry", "ACTIVE"),
                regime_at_exit=s_regime,
            )
            exits.append({"symbol": sym, "pnl": round(pnl, 2), "reason": "regime_exit"})
            log.info(f"  Shadow EXIT: {sym} @ {exit_price:.2f} | PnL: Rs.{pnl:+.2f}")
        state["positions"] = {}

    # ── Step 2: Check SL on open positions (ACTIVE regime) ───────────────────
    elif s_regime == "ACTIVE" and state["positions"]:
        price_map = {c["symbol"]: c["price"] for c in candidates}
        for sym, pos in list(state["positions"].items()):
            ltp = price_map.get(sym, 0)
            if ltp <= 0:
                continue
            sl = pos.get("sl_price", pos["entry"] * (1 - SL_PCT))
            if ltp <= sl:
                pnl = (ltp - pos["entry"]) * pos["qty"]
                state["cash"] += ltp * pos["qty"]
                state["pnl"]  += pnl
                state["trades"].append({
                    "symbol": sym, "entry": pos["entry"], "exit": ltp,
                    "qty": pos["qty"], "pnl": round(pnl, 2),
                    "time": today, "exit_reason": "Stop Loss",
                })
                _record_trade(
                    symbol=sym,
                    entry_date=pos.get("entry_date", today),
                    exit_date=today,
                    entry_price=pos["entry"],
                    exit_price=ltp,
                    qty=pos["qty"],
                    exit_reason=f"Stop Loss hit ({ltp:.2f} <= {sl:.2f})",
                    regime_at_entry=pos.get("regime_at_entry", "ACTIVE"),
                    regime_at_exit=s_regime,
                )
                exits.append({"symbol": sym, "pnl": round(pnl, 2), "reason": "sl_hit"})
                del state["positions"][sym]
                log.info(f"  Shadow SL: {sym} @ {ltp:.2f} | PnL: Rs.{pnl:+.2f}")

    # ── Step 3: Enter new positions if ACTIVE + rebalance due ────────────────
    if s_regime == "ACTIVE" and rebal_due and candidates:
        already_held = set(state["positions"].keys())
        for c in candidates:
            sym = c["symbol"]
            if sym in already_held:
                continue
            price = c.get("price", 0)
            if price <= 0:
                continue
            qty = max(1, int(PER_POS / price))
            cost = price * qty
            if cost > state["cash"]:
                log.info(f"  Shadow: insufficient cash for {sym} (need Rs.{cost:.0f}, have Rs.{state['cash']:.0f})")
                continue
            sl_price = round(price * (1 - SL_PCT), 2)
            state["cash"] -= cost
            state["positions"][sym] = {
                "entry":           price,
                "qty":             qty,
                "sl_price":        sl_price,
                "entry_date":      today,
                "regime_at_entry": s_regime,
            }
            entries.append({"symbol": sym, "price": price, "qty": qty})
            log.info(f"  Shadow BUY: {sym} @ {price:.2f} qty={qty} SL={sl_price:.2f}")

    # ── Step 4: Compute portfolio value ──────────────────────────────────────
    price_map = {c["symbol"]: c["price"] for c in candidates}
    invested = sum(
        pos["entry"] * pos["qty"]   # use entry as proxy (no live LTP in EOD shadow)
        for pos in state["positions"].values()
    )
    portfolio_value = state["cash"] + invested

    state["last_run"] = today
    _save_state(state)

    summary = {
        "date":            today,
        "shadow_regime":   s_regime,
        "prod_regime":     prod_regime,
        "positions":       len(state["positions"]),
        "cash":            round(state["cash"], 2),
        "portfolio_value": round(portfolio_value, 2),
        "total_pnl":       round(state["pnl"], 2),
        "total_trades":    len(state["trades"]),
        "exits_today":     exits,
        "entries_today":   entries,
        "return_pct":      round((portfolio_value - SHADOW_CAPITAL) / SHADOW_CAPITAL * 100, 2),
    }
    log.info(f"Shadow summary: regime={s_regime} positions={summary['positions']} "
             f"portfolio=Rs.{portfolio_value:.0f} pnl=Rs.{state['pnl']:+.0f}")
    return summary


def show_shadow_status():
    state = _load_state()
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  SHADOW ENGINE STATUS — {date.today()}")
    print(sep)
    cap = SHADOW_CAPITAL
    pv  = state["cash"] + sum(p["entry"] * p["qty"] for p in state["positions"].values())
    print(f"  Strategy         : RS60/EP40 + 50-DMA regime")
    print(f"  Start capital    : Rs.{cap:,.0f}")
    print(f"  Portfolio value  : Rs.{pv:,.0f}")
    print(f"  Total PnL        : Rs.{state['pnl']:+,.2f}")
    print(f"  Return           : {(pv - cap) / cap * 100:+.2f}%")
    print(f"  Open positions   : {len(state['positions'])}")
    print(f"  Completed trades : {len(state['trades'])}")
    if state["positions"]:
        print(f"\n  {'Symbol':<14} {'Qty':>5} {'Entry':>10} {'SL':>10} {'Since'}")
        print(f"  {'-'*50}")
        for sym, pos in state["positions"].items():
            print(f"  {sym:<14} {pos['qty']:>5} Rs.{pos['entry']:>8,.2f} "
                  f"Rs.{pos['sl_price']:>8,.2f} {pos.get('entry_date','')}")
    print(sep)


if __name__ == "__main__":
    import sys
    if "--status" in sys.argv:
        show_shadow_status()
    else:
        print("Usage: python shadow_engine.py --status")
        print("       (shadow_engine is run automatically by auto_daily.py)")
