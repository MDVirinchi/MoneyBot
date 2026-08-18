"""
Upstox Algorithmic Trading Bot
Strategy: EMA crossover + RSI filter + News sentiment on 1500+ NSE stocks
"""

import time
import json
import logging
import requests
import sys
from datetime import datetime, timedelta
from pathlib import Path
import config
from indicators import score_signals, kelly_position_size, compute_stats
from backtest import PaperTrader
from risk_manager import RiskManager
from trade_journal import record_trade as journal_record

log = logging.getLogger("trading_bot")
if not log.handlers:
    log.setLevel(logging.INFO)
    _fmt = logging.Formatter("%(asctime)s [TRADE] %(message)s")
    _fh = logging.FileHandler("moneybot_trading.log", encoding="utf-8")
    _fh.setFormatter(_fmt)
    _sh = logging.StreamHandler(open(sys.stdout.fileno(),
        mode="w", encoding="utf-8", buffering=1, closefd=False))
    _sh.setFormatter(_fmt)
    log.addHandler(_fh)
    log.addHandler(_sh)
    log.propagate = False

STATE_FILE = Path("trading_state.json")

# How many stocks to scan per cycle (scan in batches to avoid rate limits)
BATCH_SIZE = 50
# Minimum news confidence to let news override a weak EMA signal
NEWS_CONFIDENCE_THRESHOLD = 0.70
# Seconds between full scan cycles
SCAN_INTERVAL = 1800  # 30 minutes


class UpstoxClient:
    BASE = "https://api.upstox.com/v2"

    def __init__(self):
        self.token = config.UPSTOX_ACCESS_TOKEN
        if not self.token:
            self.token = self._auth_flow()

    def _auth_flow(self):
        import webbrowser
        from http.server import HTTPServer, BaseHTTPRequestHandler
        from urllib.parse import urlparse, parse_qs

        auth_url = (
            f"https://api.upstox.com/v2/login/authorization/dialog"
            f"?response_type=code&client_id={config.UPSTOX_API_KEY}"
            f"&redirect_uri={config.UPSTOX_REDIRECT_URI}"
        )
        log.info("Opening browser for Upstox login...")
        webbrowser.open(auth_url)

        code_holder = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                qs = parse_qs(urlparse(self.path).query)
                if "code" in qs:
                    code_holder["code"] = qs["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Login successful. You can close this tab.")
            def log_message(self, *a): pass

        srv = HTTPServer(("localhost", 8080), Handler)
        srv.handle_request()

        resp = requests.post(
            f"{self.BASE}/login/authorization/token",
            data={
                "code": code_holder["code"],
                "client_id": config.UPSTOX_API_KEY,
                "client_secret": config.UPSTOX_API_SECRET,
                "redirect_uri": config.UPSTOX_REDIRECT_URI,
                "grant_type": "authorization_code",
            }
        ).json()

        token = resp["access_token"]
        cfg_path = Path("config.py")
        import re as _re
        old_text = cfg_path.read_text(encoding="utf-8")
        new_text = _re.sub(
            r'UPSTOX_ACCESS_TOKEN\s*=\s*"[^"]*"',
            f'UPSTOX_ACCESS_TOKEN = "{token}"',
            old_text
        )
        cfg_path.write_text(new_text, encoding="utf-8")
        return token

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def get_candles(self, instrument, interval="30minute", days=30):
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        url = f"{self.BASE}/historical-candle/{instrument}/{interval}/{to_date}/{from_date}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=10)
            data = r.json()
            return data.get("data", {}).get("candles", [])
        except Exception as e:
            log.debug(f"get_candles failed for {instrument}: {e}")
            return []

    def get_ltp(self, instruments: list):
        joined = ",".join(instruments)
        try:
            r = requests.get(
                f"{self.BASE}/market-quote/ltp",
                params={"instrument_key": joined},
                headers=self._headers(),
                timeout=10
            )
            return r.json().get("data", {})
        except Exception:
            return {}

    def get_portfolio(self):
        try:
            r = requests.get(f"{self.BASE}/portfolio/short-term-positions", headers=self._headers(), timeout=10)
            return r.json().get("data", [])
        except Exception:
            return []

    def get_funds(self):
        try:
            r = requests.get(f"{self.BASE}/user/get-funds-and-margin", headers=self._headers(), timeout=10)
            return r.json().get("data", {})
        except Exception:
            return {}

    def place_order(self, instrument, qty, side, order_type="MARKET", price=0):
        payload = {
            "quantity": qty,
            "product": "D",
            "validity": "DAY",
            "price": price,
            "tag": "moneybot",
            "instrument_token": instrument,
            "order_type": order_type,
            "transaction_type": side,
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False,
        }
        try:
            r = requests.post(
                f"{self.BASE}/order/place",
                json=payload,
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
                    log.warning(f"Order {order_id} not confirmed filled — treating as accepted")
                return result
            else:
                log.warning(f"Order REJECTED: {side} {qty}x {instrument} -> {result}")
            return result
        except Exception as e:
            log.error(f"Order placement failed: {e}")
            return {}

    def _wait_for_fill(self, order_id, instrument, qty, side, max_wait=10):
        """Poll order status until filled, rejected, or timeout.

        Upstox order statuses:
          'complete'         → fully filled
          'rejected'         → broker/exchange rejected after acceptance
          'cancelled'        → user or system cancelled
          'open'             → still waiting (limit order)
          'trigger pending'  → SL/SL-M waiting for trigger

        For MARKET orders, 'complete' usually arrives within 1-2 seconds.
        Returns enriched result dict with fill details, or None on failure.
        """
        for attempt in range(max_wait):
            time.sleep(1)
            try:
                r = requests.get(
                    f"{self.BASE}/order/details",
                    params={"order_id": order_id},
                    headers=self._headers(),
                    timeout=10
                )
                data = r.json().get("data", {})
                status = data.get("status", "").lower()

                if status == "complete":
                    fill_price = float(data.get("average_price", 0))
                    fill_qty = int(data.get("filled_quantity", qty))
                    log.info(f"Order FILLED: {side} {fill_qty}x {instrument} @ Rs.{fill_price:.2f} (order_id={order_id})")
                    return {
                        "status": "success",
                        "fill_confirmed": True,
                        "fill_price": fill_price,
                        "fill_qty": fill_qty,
                        "order_id": order_id,
                    }
                elif status in ("rejected", "cancelled"):
                    log.warning(f"Order {status.upper()}: {side} {qty}x {instrument} (order_id={order_id})")
                    return {"status": status, "fill_confirmed": False, "order_id": order_id}
                else:
                    log.debug(f"Order {order_id} status={status}, waiting... ({attempt+1}/{max_wait})")
            except Exception as e:
                log.debug(f"Order status check failed: {e}")

        log.warning(f"Order {order_id} status unknown after {max_wait}s — check broker manually")
        return None


# Indicators are now in indicators.py (EMA, RSI, Heikin-Ashi, Guppy MMA,
# Kelly Criterion, slope/concavity, large-move detection, multi-signal scorer)


# ── State management ──────────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"positions": {}, "trades": [], "pnl": 0}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))

MISMATCH_FILE = Path("reconcile_mismatches.json")

def _load_mismatches():
    if MISMATCH_FILE.exists():
        try:
            return json.loads(MISMATCH_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_mismatches(m):
    MISMATCH_FILE.write_text(json.dumps(m, indent=2, default=str))

REQUIRED_CONSECUTIVE_MISMATCHES = 2

def reconcile_with_broker(client, state):
    """Sync local position state with broker reality.

    Safety: quantity corrections require the SAME mismatch to appear on
    2 consecutive reconciliation runs. This prevents a single stale API
    response from corrupting local state.

    Handles:
      - Phantom positions (local says held, broker doesn't) → removed after 2 checks
      - Quantity mismatches (partial fills, split fills) → corrected after 2 checks
      - Rejected/cancelled orders → phantom removal covers this
      - Broker-only positions (manual trades) → logged, not adopted
    """
    try:
        broker_positions = client.get_portfolio()
        if not broker_positions:
            return
        broker_map = {}
        for p in broker_positions:
            key = p.get("instrument_token", "")
            qty = p.get("quantity", 0)
            if key:
                broker_map[key] = qty

        local_keys = set(state["positions"].keys())
        broker_keys = set(broker_map.keys())
        prev_mismatches = _load_mismatches()
        curr_mismatches = {}
        changed = False

        # 1. Phantom positions: local has it, broker doesn't
        phantoms = local_keys - broker_keys
        for inst in phantoms:
            sym = state["positions"][inst].get("plain", inst.split("|")[-1])
            mkey = f"phantom:{inst}"
            prev_count = prev_mismatches.get(mkey, 0)
            if prev_count + 1 >= REQUIRED_CONSECUTIVE_MISMATCHES:
                log.warning(f"RECONCILE: {sym} phantom confirmed ({prev_count+1} consecutive checks) — removing")
                del state["positions"][inst]
                changed = True
            else:
                curr_mismatches[mkey] = prev_count + 1
                log.info(f"RECONCILE: {sym} not in broker (check {prev_count+1}/{REQUIRED_CONSECUTIVE_MISMATCHES}) — will remove if persists")

        # 2. Quantity mismatches
        for inst in local_keys & broker_keys:
            local_qty = state["positions"][inst].get("qty", 0)
            broker_qty = broker_map[inst]
            if broker_qty == 0:
                mkey = f"zero:{inst}"
                prev_count = prev_mismatches.get(mkey, 0)
                if prev_count + 1 >= REQUIRED_CONSECUTIVE_MISMATCHES:
                    sym = state["positions"][inst].get("plain", inst.split("|")[-1])
                    log.warning(f"RECONCILE: {sym} broker qty=0 confirmed — removing")
                    del state["positions"][inst]
                    changed = True
                else:
                    curr_mismatches[mkey] = prev_count + 1
            elif broker_qty != local_qty:
                mkey = f"qty:{inst}:{broker_qty}"
                prev_count = prev_mismatches.get(mkey, 0)
                if prev_count + 1 >= REQUIRED_CONSECUTIVE_MISMATCHES:
                    sym = state["positions"][inst].get("plain", inst.split("|")[-1])
                    log.warning(f"RECONCILE: {sym} qty mismatch confirmed — local={local_qty}, broker={broker_qty}. Correcting.")
                    state["positions"][inst]["qty"] = broker_qty
                    changed = True
                else:
                    curr_mismatches[mkey] = prev_count + 1
                    sym = state["positions"][inst].get("plain", inst.split("|")[-1])
                    log.info(f"RECONCILE: {sym} qty mismatch local={local_qty} broker={broker_qty} (check {prev_count+1}/{REQUIRED_CONSECUTIVE_MISMATCHES})")

        # 3. Broker-only positions: logged, not adopted
        for inst in broker_keys - local_keys:
            log.info(f"RECONCILE: {inst.split('|')[-1]} in broker but not local (manual trade?) — not adopting")

        _save_mismatches(curr_mismatches)
        if changed:
            save_state(state)
            log.info("Reconciliation complete — state updated.")
    except Exception as e:
        log.warning(f"Broker reconciliation skipped: {e}")


# ── News integration ──────────────────────────────────────────────────────────

_news_signals_cache = {"signals": [], "fetched_at": None}
_NEWS_REFRESH_SECONDS = 900  # refresh news every 15 minutes

def get_cached_news_signals(plain_symbols: list) -> list:
    """Fetch news signals, caching for 15 min to avoid hammering APIs."""
    now = datetime.now()
    cache_age = (now - _news_signals_cache["fetched_at"]).total_seconds() if _news_signals_cache["fetched_at"] else 9999
    if _news_signals_cache["fetched_at"] is None or cache_age > _NEWS_REFRESH_SECONDS:
        try:
            from news_analyzer import get_news_signals
            signals = get_news_signals(plain_symbols)
            _news_signals_cache["signals"] = signals
            _news_signals_cache["fetched_at"] = now
            log.info(f"News signals refreshed: {len(signals)} signals found")
        except Exception as e:
            log.warning(f"News fetch failed: {e}")
    return _news_signals_cache["signals"]

def find_news_signal_for(plain_symbol: str, news_signals: list):
    """Return the news signal dict for a symbol if it exists, else None."""
    for sig in news_signals:
        if sig.get("symbol", "").upper() == plain_symbol.upper():
            return sig
    return None

def record_reaction_after_trade(instrument_key: str, plain_symbol: str,
                                  entry_price: float, exit_price: float,
                                  news_sentiment: str):
    """After a trade closes, record how the stock reacted to that news."""
    if not news_sentiment:
        return
    try:
        from news_analyzer import record_news_reaction
        record_news_reaction(
            symbol=plain_symbol,
            news_title="[auto-recorded from trade]",
            sentiment=news_sentiment,
            price_before=entry_price,
            price_after=exit_price,
            hours_later=2
        )
    except Exception as e:
        log.debug(f"Could not record news reaction: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    if not config.UPSTOX_API_KEY:
        log.error("Set UPSTOX_API_KEY in config.py first.")
        return

    client = UpstoxClient()
    state  = load_state()
    paper  = PaperTrader(capital=config.TRADING_CAPITAL_INR)
    risk   = RiskManager(capital=config.TRADING_CAPITAL_INR)
    reconcile_with_broker(client, state)

    # Build/load the stock universe
    try:
        from stock_universe import get_all_symbols, get_plain_symbols
        all_instruments = get_all_symbols()       # e.g. ["NSE_EQ|RELIANCE", ...]
        all_plain       = get_plain_symbols()     # e.g. ["RELIANCE", ...]
        log.info(f"Stock universe loaded: {len(all_instruments)} stocks (Large+Mid+Small cap)")
    except Exception as e:
        log.warning(f"Could not load stock universe, using fallback list: {e}")
        all_instruments = config.TRADING_SYMBOLS
        all_plain = [s.split("|")[-1] for s in config.TRADING_SYMBOLS]

    log.info("Trading bot started. Scanning every 30 minutes during market hours.")

    # Track which news sentiment was active when we bought a stock
    position_news_sentiment = {}

    while True:
        now = datetime.now()
        # Only trade during NSE market hours (9:15 – 15:30 IST Mon-Fri)
        if now.weekday() >= 5 or not (9 * 60 + 15 <= now.hour * 60 + now.minute <= 15 * 60 + 30):
            log.info("Market closed. Sleeping 5 min.")
            time.sleep(300)
            continue

        try:
            funds = client.get_funds()
            available = float(funds.get("equity", {}).get("available_margin", 0))
            log.info(f"Available funds: Rs.{available:.2f} | Open positions: {len(state['positions'])}")

            # 1. Refresh news signals once per cycle
            news_signals = get_cached_news_signals(all_plain)
            news_symbol_set = {s["symbol"].upper() for s in news_signals}
            if news_signals:
                log.info(f"Active news signals: {[s['symbol']+':'+s['action'] for s in news_signals[:5]]}")

            # 2. Prioritize: news-mentioned stocks come first, then batch of others
            priority = [inst for inst in all_instruments
                        if inst.split("|")[-1].upper() in news_symbol_set]
            rest = [inst for inst in all_instruments
                    if inst not in priority]

            # Scan priority stocks + first BATCH_SIZE of the rest
            to_scan = priority + rest[:BATCH_SIZE]
            log.info(f"Scanning {len(to_scan)} stocks this cycle ({len(priority)} news-prioritized)")

            # ── PERIODIC RECONCILIATION: catch late fills and broker-side changes ──
            # Runs every cycle (every 30 min), not just on startup.
            # Catches: orders that filled after our 10s timeout, manual broker
            # actions, partial fills that completed, positions closed externally.
            reconcile_with_broker(client, state)

            # ── EXIT MONITORING: evaluate ALL open positions BEFORE scanning new ones ──
            # Fetches LTP for every held instrument in ONE API call so that every
            # stop-loss and take-profit is checked every cycle — not just the one
            # stock that happens to come up in the scan batch (Bug A fix).
            # Only monitor positions that are NOT already pending sell confirmation
            active_for_exit = {k: v for k, v in state["positions"].items()
                               if not v.get("pending_sell")}
            if active_for_exit:
                held_instruments = list(active_for_exit.keys())
                held_ltp_raw = client.get_ltp(held_instruments)
                held_ltp_map = {
                    k: v.get("last_price", 0)
                    for k, v in held_ltp_raw.items()
                    if isinstance(v, dict) and v.get("last_price", 0) > 0
                }
                cycle_exits = risk.check_exits(state["positions"], held_ltp_map)
                for ex in cycle_exits:
                    pos = state["positions"].get(ex["instrument"])
                    if not pos:
                        continue
                    p_sym = pos.get("plain", ex["instrument"].split("|")[-1])
                    result = client.place_order(ex["instrument"], pos["qty"], "SELL")
                    if result.get("status") in ("success", "complete") and result.get("fill_confirmed"):
                        exit_price = result.get("fill_price", ex["ltp"])
                        exit_qty = result.get("fill_qty", pos["qty"])
                        pnl = (exit_price - pos["entry"]) * exit_qty
                        state["pnl"] += pnl
                        state["trades"].append({
                            "instrument": ex["instrument"], "symbol": p_sym,
                            "entry": pos["entry"], "exit": exit_price,
                            "qty": exit_qty, "pnl": round(pnl, 2),
                            "time": str(now), "exit_reason": ex["reason"]
                        })
                        risk.record_trade(pnl, p_sym)
                        risk.clear_trailing_high(ex["instrument"])
                        record_reaction_after_trade(ex["instrument"], p_sym,
                            pos["entry"], ex["ltp"], pos.get("news_sentiment"))
                        del state["positions"][ex["instrument"]]
                        log.info(f"RISK EXIT {p_sym} | {ex['reason']} | PnL: Rs.{pnl:.2f}")
                        try:
                            journal_record(
                                symbol=p_sym, instrument=ex["instrument"],
                                entry_date=pos.get("time", "")[:10], exit_date=str(now.date()),
                                entry_price=pos["entry"], exit_price=exit_price,
                                qty=exit_qty, net_pnl=pnl, exit_reason=ex["reason"],
                                signal_score=pos.get("score", 0), system="B",
                                order_id_exit=result.get("order_id", ""),
                            )
                        except Exception:
                            pass
                    elif result.get("status") in ("success",) and not result.get("fill_confirmed"):
                        state["positions"][ex["instrument"]]["pending_sell"] = True
                        log.warning(f"SELL {p_sym} not confirmed — marked pending_sell. Will resolve on reconciliation.")
                if cycle_exits:
                    save_state(state)
                    funds = client.get_funds()
                    available = float(funds.get("equity", {}).get("available_margin", 0))

            # Count only ACTIVE positions (exclude pending_sell) for capacity checks
            active_positions = {k: v for k, v in state["positions"].items()
                                if not v.get("pending_sell")}

            for instrument in to_scan:
                # Respect max open positions (pending_sell not counted)
                if len(active_positions) >= config.MAX_OPEN_POSITIONS:
                    log.info("Max open positions reached. Skipping remaining stocks.")
                    break

                plain = instrument.split("|")[-1]  # e.g. "RELIANCE"
                news_sig = find_news_signal_for(plain, news_signals)

                # Get candles for multi-strategy scoring
                candles = client.get_candles(instrument)
                if not candles or len(candles) < 30:
                    time.sleep(0.2)
                    continue

                # ── Multi-strategy signal (EMA+RSI+HA+Guppy+slope+concavity+large-move)
                scored = score_signals(candles)
                tech_action = scored["action"]   # BUY / SELL / HOLD
                tech_score  = scored["score"]

                in_position = instrument in state["positions"] and not state["positions"].get(instrument, {}).get("pending_sell")

                # ── Combine with news signal
                final_sig = None
                final_reason = []

                if tech_action in ("BUY", "SELL") and tech_score >= 0.40:
                    final_sig = tech_action
                    final_reason = scored["reasons"]

                if news_sig:
                    news_action     = news_sig["action"]
                    news_confidence = news_sig["confidence"]
                    if news_confidence >= NEWS_CONFIDENCE_THRESHOLD:
                        if final_sig is None:
                            final_sig = news_action
                            final_reason = [f"News signal: {news_sig['reason']}"]
                        elif final_sig == news_action:
                            tech_score = min(1.0, tech_score + 0.15)  # boost on agreement
                            final_reason.append(f"News confirms: {news_sig['reason']}")
                        else:
                            log.info(f"{plain}: Tech={final_sig} vs News={news_action} — conflict, skipping")
                            final_sig = None

                if not final_sig or final_sig == "HOLD":
                    time.sleep(0.2)
                    continue

                # Get current price
                ltp_data = client.get_ltp([instrument])
                ltp_entry = next(iter(ltp_data.values()), {}) if ltp_data else {}
                ltp = ltp_entry.get("last_price", 0)
                if ltp <= 0:
                    continue

                if final_sig == "BUY" and not in_position:
                    if available < ltp:
                        log.debug(f"Insufficient funds for {plain} @ Rs.{ltp:.2f}")
                        continue

                    # ── Risk gate ─────────────────────────────────────────────
                    ok, reason = risk.can_trade(state["positions"], available)
                    if not ok:
                        log.info(f"Risk blocked BUY {plain}: {reason}")
                        continue

                    # ── Kelly Criterion sizing ────────────────────────────────
                    trade_stats = compute_stats(state["trades"])
                    invest_amt  = kelly_position_size(
                        available, trade_stats["win_rate"],
                        trade_stats["avg_win_pct"], trade_stats["avg_loss_pct"],
                        aggressiveness=0.5
                    )
                    qty = risk.position_size(ltp, available, invest_amt)

                    result = client.place_order(instrument, qty, "BUY")
                    if result.get("status") in ("success", "complete"):
                        if not result.get("fill_confirmed"):
                            log.warning(f"BUY {plain} order not confirmed filled (fill_confirmed={result.get('fill_confirmed')}) — NOT adding to positions")
                            continue
                        actual_price = result.get("fill_price", ltp)
                        actual_qty = result.get("fill_qty", qty)
                        state["positions"][instrument] = {
                            "qty": actual_qty, "entry": actual_price, "time": str(now),
                            "plain": plain,
                            "news_sentiment": news_sig["action"] if news_sig else None,
                            "score": tech_score,
                            "order_id": result.get("order_id", ""),
                        }
                        available -= actual_price * actual_qty
                        log.info(f"BOUGHT {actual_qty}x {plain} @ Rs.{actual_price:.2f} | score={tech_score:.2f} | {' | '.join(final_reason[:2])}")

                elif final_sig == "SELL" and in_position:
                    pos = state["positions"][instrument]
                    result = client.place_order(instrument, pos["qty"], "SELL")
                    if result.get("status") in ("success", "complete") and result.get("fill_confirmed"):
                        exit_price = result.get("fill_price", ltp)
                        exit_qty = result.get("fill_qty", pos["qty"])
                        pnl = (exit_price - pos["entry"]) * exit_qty
                        state["pnl"] += pnl
                        state["trades"].append({
                            "instrument": instrument, "symbol": plain,
                            "entry": pos["entry"], "exit": exit_price,
                            "qty": exit_qty, "pnl": round(pnl, 2),
                            "time": str(now), "exit_reason": "Signal:SELL"
                        })
                        risk.record_trade(pnl, plain)
                        risk.clear_trailing_high(instrument)
                        record_reaction_after_trade(instrument, plain,
                            pos["entry"], ltp, pos.get("news_sentiment"))
                        del state["positions"][instrument]
                        log.info(f"SOLD {plain} | PnL: Rs.{pnl:.2f} | Total PnL: Rs.{state['pnl']:.2f}")
                        try:
                            journal_record(
                                symbol=plain, instrument=instrument,
                                entry_date=pos.get("time", "")[:10], exit_date=str(now.date()),
                                entry_price=pos["entry"], exit_price=exit_price,
                                qty=exit_qty, net_pnl=pnl, exit_reason="Signal:SELL",
                                signal_score=pos.get("score", 0), system="B",
                                order_id_exit=result.get("order_id", ""),
                            )
                        except Exception:
                            pass
                    elif result.get("status") in ("success",) and not result.get("fill_confirmed"):
                        state["positions"][instrument]["pending_sell"] = True
                        log.warning(f"SELL {plain} not confirmed — marked pending_sell. Will resolve on reconciliation.")

                # Paper trade tick (mirrors real bot, no real orders)
                paper.tick(instrument, plain, candles)

                save_state(state)
                time.sleep(0.3)  # be gentle on API rate limits

        except Exception as e:
            log.error(f"Error in trading loop: {e}", exc_info=True)

        log.info(f"Cycle done. Next scan in 30 min. Total PnL so far: Rs.{state['pnl']:.2f}")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    run()
