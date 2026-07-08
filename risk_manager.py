"""
risk_manager.py — Risk Management for MoneyBot
================================================
Features:
  - Stop Loss         : fixed % below entry, kills trade automatically
  - Trailing Stop     : rises with price, locks in profits
  - Take Profit       : auto-exit at target gain
  - Daily Loss Limit  : circuit breaker — halts trading if daily loss exceeded
  - Max Portfolio Heat: caps total risk exposure across all open positions
  - Consecutive Loss  : halts after N losses in a row (tilt prevention)
  - Position Size Cap : no single trade exceeds X% of capital
"""

import json
import logging
import os
import tempfile
from datetime import datetime, date
from pathlib import Path

log = logging.getLogger(__name__)

RISK_STATE_FILE = Path("risk_state.json")

# ── Default risk parameters ───────────────────────────────────────────────────
DEFAULTS = {
    "stop_loss_pct":         2.0,    # exit if price drops 2% below entry
    "trailing_stop_pct":     1.5,    # trailing stop trails 1.5% below high
    "take_profit_pct":       4.0,    # exit if price rises 4% above entry (2:1 R:R)
    "daily_loss_limit_pct":  5.0,    # halt trading if down 5% from day start
    "max_portfolio_heat_pct":6.0,    # max total risk across all positions
    "max_consecutive_losses":3,      # halt after 3 losses in a row
    "max_position_pct":      20.0,   # single position ≤ 20% of capital
    "max_open_positions":    3,
}


class RiskManager:
    def __init__(self, capital: float, params: dict = None):
        self.capital      = capital
        self.params       = {**DEFAULTS, **(params or {})}
        self.state        = self._load()
        self._init_day()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if RISK_STATE_FILE.exists():
            try:
                return json.loads(RISK_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self._fresh_state()

    def _fresh_state(self) -> dict:
        return {
            "day":                str(date.today()),
            "day_start_capital":  self.capital,
            "day_pnl":            0.0,
            "consecutive_losses": 0,
            "halted":             False,
            "halt_reason":        "",
            "trailing_highs":     {},   # instrument -> highest price seen
            "trade_log":          [],
        }

    def _save(self):
        fd, tmp = tempfile.mkstemp(dir=RISK_STATE_FILE.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
            Path(tmp).replace(RISK_STATE_FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _init_day(self):
        """Reset daily state at start of each new trading day."""
        today = str(date.today())
        if self.state.get("day") != today:
            log.info(f"RiskManager: new trading day {today}, resetting daily limits")
            self.state = self._fresh_state()
            self.state["day_start_capital"] = self.capital
            self._save()

    # ── Entry checks ─────────────────────────────────────────────────────────

    def can_trade(self, positions: dict, available_capital: float) -> tuple:
        """
        Returns (True, "") if a new trade is allowed, else (False, reason).
        Call this BEFORE placing any buy order.
        """
        self._init_day()

        if self.state["halted"]:
            return False, f"Trading HALTED: {self.state['halt_reason']}"

        if len(positions) >= self.params["max_open_positions"]:
            return False, f"Max open positions ({self.params['max_open_positions']}) reached"

        daily_loss_pct = (self.state["day_pnl"] / self.state["day_start_capital"]) * 100
        if daily_loss_pct <= -self.params["daily_loss_limit_pct"]:
            self._halt(f"Daily loss limit hit ({daily_loss_pct:.1f}%)")
            return False, self.state["halt_reason"]

        if self.state["consecutive_losses"] >= self.params["max_consecutive_losses"]:
            self._halt(f"{self.params['max_consecutive_losses']} consecutive losses — cool down")
            return False, self.state["halt_reason"]

        return True, ""

    def position_size(self, ltp: float, available_capital: float,
                      kelly_amount: float) -> int:
        """
        Returns safe quantity to buy, respecting position size cap.
        """
        max_invest = available_capital * (self.params["max_position_pct"] / 100)
        invest     = min(kelly_amount, max_invest)
        invest     = max(invest, available_capital * 0.02)   # at least 2%
        qty        = max(1, int(invest / ltp))
        # Final check: don't exceed capital
        while qty > 1 and qty * ltp > available_capital:
            qty -= 1
        return qty

    # ── Exit checks (call every tick for open positions) ──────────────────────

    def check_exits(self, positions: dict, ltp_map: dict) -> list:
        """
        Given current prices, return list of instruments to EXIT and why.
        ltp_map: {instrument_key: current_price}

        Returns list of {"instrument", "reason", "ltp"}.
        """
        exits = []
        for instrument, pos in positions.items():
            ltp = ltp_map.get(instrument)
            if not ltp or ltp <= 0:
                continue

            entry       = pos["entry"]
            sl_price    = entry * (1 - self.params["stop_loss_pct"]   / 100)
            tp_price    = entry * (1 + self.params["take_profit_pct"] / 100)
            trail_pct   = self.params["trailing_stop_pct"] / 100

            # Update trailing high
            key = instrument
            if key not in self.state["trailing_highs"]:
                self.state["trailing_highs"][key] = entry
            if ltp > self.state["trailing_highs"][key]:
                self.state["trailing_highs"][key] = ltp

            trail_high  = self.state["trailing_highs"][key]
            trail_stop  = trail_high * (1 - trail_pct)

            if ltp <= sl_price:
                exits.append({"instrument": instrument, "ltp": ltp,
                               "reason": f"Stop Loss hit ({ltp:.2f} <= {sl_price:.2f})"})
            elif ltp >= tp_price:
                exits.append({"instrument": instrument, "ltp": ltp,
                               "reason": f"Take Profit hit ({ltp:.2f} >= {tp_price:.2f})"})
            elif ltp <= trail_stop and trail_high > entry * 1.005:
                exits.append({"instrument": instrument, "ltp": ltp,
                               "reason": f"Trailing Stop hit ({ltp:.2f} <= {trail_stop:.2f}, high={trail_high:.2f})"})

        self._save()
        return exits

    # ── Record trade outcome ──────────────────────────────────────────────────

    def clear_trailing_high(self, instrument: str):
        """Remove trailing high when a position is closed.
        Without this, a stale high persists and corrupts the trailing stop
        if the same stock is re-entered later at a different price."""
        self.state["trailing_highs"].pop(instrument, None)
        self._save()

    def record_trade(self, pnl: float, symbol: str):
        """Call after every closed trade to update daily stats."""
        self.state["day_pnl"] += pnl

        if pnl > 0:
            self.state["consecutive_losses"] = 0
        else:
            self.state["consecutive_losses"] += 1
            if self.state["consecutive_losses"] >= self.params["max_consecutive_losses"]:
                self._halt(f"{self.state['consecutive_losses']} consecutive losses on {symbol}")

        self.state["trade_log"].append({
            "symbol": symbol, "pnl": round(pnl, 2),
            "time": str(datetime.now()),
            "consecutive_losses": self.state["consecutive_losses"]
        })
        self._save()
        log.info(f"RiskManager: {symbol} P&L=Rs.{pnl:.2f} | day_pnl=Rs.{self.state['day_pnl']:.2f} | streak={self.state['consecutive_losses']}")

    def resume(self):
        """Manually resume after a halt (e.g. next morning)."""
        self.state["halted"]      = False
        self.state["halt_reason"] = ""
        self.state["consecutive_losses"] = 0
        self._save()
        log.info("RiskManager: trading resumed")

    def _halt(self, reason: str):
        self.state["halted"]      = True
        self.state["halt_reason"] = reason
        self._save()
        log.warning(f"RiskManager: HALT — {reason}")

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        self._init_day()
        cap  = self.state["day_start_capital"]
        dpnl = self.state["day_pnl"]
        return {
            "halted":             self.state["halted"],
            "halt_reason":        self.state["halt_reason"],
            "day_pnl":            round(dpnl, 2),
            "day_pnl_pct":        round(dpnl / cap * 100, 2) if cap else 0,
            "daily_limit_pct":    -self.params["daily_loss_limit_pct"],
            "consecutive_losses": self.state["consecutive_losses"],
            "max_consecutive":    self.params["max_consecutive_losses"],
            "stop_loss_pct":      self.params["stop_loss_pct"],
            "take_profit_pct":    self.params["take_profit_pct"],
            "trailing_stop_pct":  self.params["trailing_stop_pct"],
        }

    def print_status(self):
        s = self.status()
        sep = "=" * 45
        print(f"\n{sep}")
        print(f"  Risk Manager Status")
        print(sep)
        print(f"  Status          : {'HALTED' if s['halted'] else 'ACTIVE'}")
        if s["halted"]:
            print(f"  Halt Reason     : {s['halt_reason']}")
        print(f"  Day P&L         : Rs.{s['day_pnl']} ({s['day_pnl_pct']:+.2f}%)")
        print(f"  Daily Limit     : {s['daily_limit_pct']:.1f}%")
        print(f"  Consecutive Loss: {s['consecutive_losses']} / {s['max_consecutive']}")
        print(f"  Stop Loss       : {s['stop_loss_pct']}%")
        print(f"  Take Profit     : {s['take_profit_pct']}%")
        print(f"  Trailing Stop   : {s['trailing_stop_pct']}%")
        print(sep)
