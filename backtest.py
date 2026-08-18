"""
backtest.py — Historical Backtesting + Paper Trading engine
============================================================
Usage:
  python backtest.py --symbol RELIANCE --days 365
  python backtest.py --symbol TCS --days 180 --capital 5000
  python backtest.py --all --days 90 --top 15
  python backtest.py --forward          (show paper trade report)
  python backtest.py --compare RELIANCE TCS INFY
"""

import argparse
import json
import math
import time
import logging
import statistics
import requests
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict

import config
from indicators import score_signals, kelly_position_size, compute_stats
from risk_manager import RiskManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BACKTEST] %(message)s")
log = logging.getLogger(__name__)

RESULTS_DIR        = Path("backtest_results")
FORWARD_STATE_FILE = Path("forward_test_state.json")
RESULTS_DIR.mkdir(exist_ok=True)

RISK_FREE_RATE  = 0.065    # 6.5% Indian 10-yr bond
TRADING_DAYS_YR = 252

# Realistic transaction cost model
BROKERAGE   = 20.0    # Rs.20 flat per order (Upstox); buy + sell = Rs.40 round-trip
STT_PCT     = 0.001   # 0.1% Securities Transaction Tax on sell-side turnover
EXCHANGE_PCT= 0.0000345 # NSE + BSE + SEBI charges per side (combined ~0.00345%)
SLIPPAGE    = 0.002   # 0.2% each way — market impact + bid-ask spread


# ==============================================================================
#  DATA FETCHER
# ==============================================================================

class DataFetcher:
    BASE = "https://api.upstox.com/v2"

    # Upstox instrument key -> Yahoo Finance ticker
    _YF_MAP = {
        "NSE_EQ|INE002A01018": "RELIANCE.NS",
        "NSE_EQ|INE467B01029": "TCS.NS",
        "NSE_EQ|INE009A01021": "INFY.NS",
        "NSE_EQ|INE040A01034": "HDFCBANK.NS",
        "NSE_EQ|INE030A01027": "SBIN.NS",
        "NSE_EQ|INE397D01024": "HCLTECH.NS",
        "NSE_EQ|INE018A01030": "ICICIBANK.NS",
        "NSE_EQ|INE062A01020": "SBILIFE.NS",
        "NSE_INDEX|Nifty 50":  "^NSEI",
    }
    _YF_INTERVAL = {
        "30minute": "30m",
        "1hour":    "1h",
        "1day":     "1d",
        "15minute": "15m",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}",
            "Accept": "application/json"
        })

    def get_candles(self, instrument: str, interval: str = "30minute",
                    days: int = 365) -> list:
        """
        Returns oldest->newest list of [ts, open, high, low, close, vol, oi].
        Tries Upstox first; falls back to yfinance if token is missing/expired.
        """
        candles = self._upstox(instrument, interval, days)
        if len(candles) >= 60:
            return candles
        # Fallback
        yf_candles = self._yfinance(instrument, interval, days)
        if yf_candles:
            src = "yfinance" if not candles else "yfinance(fallback)"
            log.info(f"{instrument}: using {src} ({len(yf_candles)} candles)")
        return yf_candles if yf_candles else candles

    def _upstox(self, instrument: str, interval: str, days: int) -> list:
        to_date   = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        url = f"{self.BASE}/historical-candle/{instrument}/{interval}/{to_date}/{from_date}"
        try:
            r = self.session.get(url, timeout=15)
            candles = r.json().get("data", {}).get("candles", [])
            return list(reversed(candles))
        except Exception as e:
            log.debug(f"Upstox fetch failed {instrument}: {e}")
            return []

    def _yfinance(self, instrument: str, interval: str, days: int) -> list:
        ticker = self._YF_MAP.get(instrument)
        if not ticker:
            # Try to derive ticker from plain symbol e.g. NSE_EQ|RELIANCE
            plain = instrument.split("|")[-1]
            ticker = f"{plain}.NS"
        yf_interval = self._YF_INTERVAL.get(interval, "30m")
        # yfinance caps intraday history: 30m/15m = 60 days, 1h = 730 days
        max_days = 59 if yf_interval in ("30m", "15m") else min(days, 729)
        fetch_days = min(days, max_days)
        try:
            import yfinance as yf
            df = yf.Ticker(ticker).history(
                period=f"{fetch_days}d", interval=yf_interval, auto_adjust=True)
            if df.empty:
                return []
            candles = []
            for ts, row in df.iterrows():
                candles.append([
                    str(ts),
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    int(row["Volume"]),
                    0,
                ])
            return candles
        except Exception as e:
            log.debug(f"yfinance fetch failed {ticker}: {e}")
            return []


# ==============================================================================
#  PERFORMANCE METRICS
# ==============================================================================

class Metrics:

    @staticmethod
    def sharpe(returns: list) -> float:
        """Annualised Sharpe Ratio."""
        if len(returns) < 2:
            return 0.0
        rf_per_trade = RISK_FREE_RATE / TRADING_DAYS_YR
        mean_r = statistics.mean(returns)
        std_r  = statistics.stdev(returns) or 1e-9
        return round((mean_r - rf_per_trade) / std_r * math.sqrt(TRADING_DAYS_YR), 3)

    @staticmethod
    def sortino(returns: list) -> float:
        """
        Sortino Ratio — like Sharpe but only penalises downside volatility.
        Better metric when strategy has many small wins and rare large losses.
        """
        if len(returns) < 2:
            return 0.0
        rf_per_trade  = RISK_FREE_RATE / TRADING_DAYS_YR
        mean_r        = statistics.mean(returns)
        downside      = [r for r in returns if r < rf_per_trade]
        if not downside:
            return float("inf")
        downside_std  = math.sqrt(sum((r - rf_per_trade) ** 2 for r in downside) / len(downside))
        if downside_std == 0:
            return float("inf")
        return round((mean_r - rf_per_trade) / downside_std * math.sqrt(TRADING_DAYS_YR), 3)

    @staticmethod
    def calmar(net_pnl_pct: float, max_dd_pct: float, years: float) -> float:
        """
        Calmar Ratio = CAGR / Max Drawdown.
        > 1.0 is acceptable, > 3.0 is excellent.
        """
        if max_dd_pct == 0 or years == 0:
            return 0.0
        cagr = ((1 + net_pnl_pct / 100) ** (1 / years) - 1) * 100
        return round(cagr / max_dd_pct, 3)

    @staticmethod
    def win_rate(trades: list) -> float:
        if not trades:
            return 0.0
        return round(sum(1 for t in trades if t["pnl"] > 0) / len(trades) * 100, 2)

    @staticmethod
    def profit_factor(trades: list) -> float:
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss   = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
        if gross_loss == 0:
            return round(gross_profit, 2) if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 3)

    @staticmethod
    def max_drawdown(equity_curve: list) -> dict:
        if len(equity_curve) < 2:
            return {"pct": 0.0, "abs": 0.0, "peak": 0.0, "trough": 0.0,
                    "recovery_bars": 0}
        peak = equity_curve[0]
        max_dd_pct = max_dd_abs = 0.0
        dd_peak = dd_trough = peak
        in_dd = False
        recovery_bars = 0
        bars_since_peak = 0

        for val in equity_curve[1:]:
            if val >= peak:
                peak = val
                bars_since_peak = 0
                in_dd = False
            else:
                bars_since_peak += 1
                dd = (peak - val) / peak * 100 if peak > 0 else 0
                if dd > max_dd_pct:
                    max_dd_pct = dd
                    max_dd_abs = peak - val
                    dd_peak    = peak
                    dd_trough  = val
                    recovery_bars = bars_since_peak

        return {
            "pct":           round(max_dd_pct, 2),
            "abs":           round(max_dd_abs, 2),
            "peak":          round(dd_peak, 2),
            "trough":        round(dd_trough, 2),
            "recovery_bars": recovery_bars,
        }

    @staticmethod
    def cagr(start: float, end: float, years: float) -> float:
        if start <= 0 or years <= 0:
            return 0.0
        return round(((end / start) ** (1 / years) - 1) * 100, 2)

    @staticmethod
    def avg_win_loss(trades: list) -> dict:
        wins   = [t["pnl"] for t in trades if t["pnl"] > 0]
        losses = [abs(t["pnl"]) for t in trades if t["pnl"] < 0]
        return {
            "avg_win":   round(statistics.mean(wins),   2) if wins   else 0,
            "avg_loss":  round(statistics.mean(losses), 2) if losses else 0,
            "ratio":     round(statistics.mean(wins) / statistics.mean(losses), 2)
                         if wins and losses else 0,
            "max_win":   round(max(wins),   2) if wins   else 0,
            "max_loss":  round(max(losses), 2) if losses else 0,
        }

    @staticmethod
    def streak(trades: list) -> dict:
        best_win = best_loss = cur_win = cur_loss = 0
        for t in trades:
            if t["pnl"] > 0:
                cur_win += 1; cur_loss = 0
                best_win = max(best_win, cur_win)
            else:
                cur_loss += 1; cur_win = 0
                best_loss = max(best_loss, cur_loss)
        return {"best_win_streak": best_win, "best_loss_streak": best_loss}

    @staticmethod
    def monthly_pnl(trades: list) -> dict:
        monthly = defaultdict(float)
        for t in trades:
            try:
                month = str(t.get("exit_time", ""))[:7]   # "YYYY-MM"
                monthly[month] += t["pnl"]
            except Exception:
                pass
        return {k: round(v, 2) for k, v in sorted(monthly.items())}

    @staticmethod
    def expectancy(trades: list) -> float:
        """Average Rs. earned per trade (positive = profitable system)."""
        if not trades:
            return 0.0
        return round(sum(t["pnl"] for t in trades) / len(trades), 2)


# ==============================================================================
#  HISTORICAL BACKTESTER
# ==============================================================================

class Backtester:

    def __init__(self, capital: float = 5000.0):
        self.initial_capital = capital
        self.fetcher         = DataFetcher()

    def run(self, instrument: str, symbol: str,
            days: int = 365, interval: str = "30minute",
            min_score: float = 0.40,
            regime_filter: bool = False,
            stop_loss_pct: float = 2.0,
            take_profit_pct: float = 4.0,
            trailing_stop_pct: float = 1.5) -> dict:
        """
        min_score        : minimum signal confidence (0.40 loose → 0.75 strict)
        regime_filter    : only BUY when Nifty 50 close > EMA21
        stop_loss_pct    : hard stop loss % below entry
        take_profit_pct  : take profit % above entry
        trailing_stop_pct: trailing stop % below running high
        """
        log.info(f"Backtesting {symbol} — {days}d {interval}  "
                 f"min_score={min_score}  regime={regime_filter}  "
                 f"SL={stop_loss_pct}%/TP={take_profit_pct}%/Trail={trailing_stop_pct}%")
        candles = self.fetcher.get_candles(instrument, interval, days)

        if len(candles) < 60:
            print(f"  {symbol}: not enough data ({len(candles)} candles). Need 60+.")
            return {"symbol": symbol, "error": "insufficient data"}

        # -- Regime filter: precompute Nifty 50 EMA21 uptrend per timestamp ----
        nifty_bullish = {}   # ts -> bool; empty dict = filter disabled
        if regime_filter:
            try:
                nifty_candles = self.fetcher.get_candles(
                    "NSE_INDEX|Nifty 50", interval, days)
                from indicators import ema as _ema
                nifty_closes = [c[4] for c in nifty_candles]
                nifty_ema21  = _ema(nifty_closes, 21)
                for idx, nc in enumerate(nifty_candles):
                    ts = nc[0]
                    close = nc[4]
                    e21   = nifty_ema21[idx] if idx < len(nifty_ema21) else None
                    nifty_bullish[ts] = (e21 is not None and close > e21)
                log.info(f"Regime filter: {sum(nifty_bullish.values())} of "
                         f"{len(nifty_bullish)} bars are Nifty-bullish")
            except Exception as e:
                log.warning(f"Regime filter fetch failed, disabling: {e}")
                nifty_bullish = {}

        # -- Simulate walk-forward ---------------------------------------------
        capital      = self.initial_capital
        position     = None
        trades       = []
        equity_curve = [capital]
        LOOKBACK     = 50

        # Risk manager in backtest mode (no file I/O)
        rm_params = {
            "stop_loss_pct":         stop_loss_pct,
            "trailing_stop_pct":     trailing_stop_pct,
            "take_profit_pct":       take_profit_pct,
            "daily_loss_limit_pct":  5.0,
            "max_consecutive_losses":3,
        }

        for i in range(LOOKBACK, len(candles)):
            window  = candles[:i]
            current = candles[i]
            ltp     = current[4]   # close of bar i — used for exit checks
            ts      = current[0]

            scored = score_signals(window)
            action = scored["action"]
            score  = scored["score"]

            # -- Risk exits on open position -----------------------------------
            # Exit at bar i close (signal triggered during this bar)
            if position:
                sl  = position["entry"] * (1 - rm_params["stop_loss_pct"]   / 100)
                tp  = position["entry"] * (1 + rm_params["take_profit_pct"] / 100)
                if position["high"] is None or ltp > position["high"]:
                    position["high"] = ltp
                trail = position["high"] * (1 - rm_params["trailing_stop_pct"] / 100)

                exit_reason = None
                if ltp <= sl:
                    exit_reason = f"StopLoss@{sl:.2f}"
                elif ltp >= tp:
                    exit_reason = f"TakeProfit@{tp:.2f}"
                elif ltp <= trail and position["high"] > position["entry"] * 1.005:
                    exit_reason = f"TrailingStop@{trail:.2f}"
                elif action == "SELL" and score >= min_score:
                    exit_reason = f"Signal:SELL(score={score:.2f})"

                if exit_reason:
                    # Realistic exit: you receive ltp minus slippage
                    exit_price   = ltp * (1 - SLIPPAGE)
                    exit_value   = position["qty"] * exit_price
                    entry_value  = position["qty"] * position["entry"]
                    # Costs: brokerage on sell + STT on sell turnover + exchange fees
                    costs = (BROKERAGE
                             + exit_value * STT_PCT
                             + exit_value * EXCHANGE_PCT)
                    pnl  = (exit_price - position["entry"]) * position["qty"] - costs
                    capital += exit_value - costs
                    ret = pnl / entry_value
                    trades.append({
                        "entry": position["entry"], "exit": exit_price,
                        "qty":   position["qty"],
                        "pnl":   round(pnl, 2),
                        "costs": round(costs, 2),
                        "return_pct": round(ret * 100, 2),
                        "entry_time":     str(position["ts"]),
                        "exit_time":      str(ts),
                        "exit_reason":    exit_reason,
                        # Indicator state at entry
                        "entry_score":    position.get("entry_score"),
                        "entry_signals":  position.get("entry_signals", {}),
                        "regime_bullish": position.get("regime_bullish"),
                    })
                    position = None

            # -- Entry ---------------------------------------------------------
            # Signal fires on bar i, execution at bar i+1 OPEN (no look-ahead)
            # Regime gate: only BUY when Nifty is above its EMA21 (if filter on)
            regime_ok = (not nifty_bullish) or nifty_bullish.get(ts, True)

            if position is None and action == "BUY" and score >= min_score and regime_ok:
                next_i = i + 1
                if next_i < len(candles):
                    exec_price = candles[next_i][1]          # open of next bar
                    # Realistic entry: you pay exec_price plus slippage
                    fill_price = exec_price * (1 + SLIPPAGE)
                    if capital >= fill_price:
                        stats  = compute_stats(trades)
                        invest = kelly_position_size(
                            capital,
                            stats["win_rate"],
                            stats["avg_win_pct"],
                            stats["avg_loss_pct"],
                            aggressiveness=0.5
                        )
                        invest = max(invest, capital * 0.02)
                        qty    = max(1, int(invest / fill_price))
                        # Entry costs: brokerage + exchange fees (no STT on buy)
                        entry_costs = BROKERAGE + (qty * fill_price * EXCHANGE_PCT)
                        total_cost  = qty * fill_price + entry_costs
                        if total_cost <= capital:
                            capital  -= total_cost
                            position  = {
                                "qty":    qty,
                                "entry":  fill_price,
                                "ts":     candles[next_i][0],
                                "high":   fill_price,
                                # Snapshot every indicator value at entry time
                                "entry_score":    round(score, 3),
                                "entry_signals":  scored["signals"].copy(),
                                "regime_bullish": regime_ok,
                            }

            # -- Equity snapshot -----------------------------------------------
            open_val = (position["qty"] * ltp) if position else 0
            equity_curve.append(capital + open_val)

        # Close open position at last bar (with realistic costs)
        if position:
            ltp         = candles[-1][4]
            exit_price  = ltp * (1 - SLIPPAGE)
            exit_value  = position["qty"] * exit_price
            entry_value = position["qty"] * position["entry"]
            costs = (BROKERAGE
                     + exit_value * STT_PCT
                     + exit_value * EXCHANGE_PCT)
            pnl  = (exit_price - position["entry"]) * position["qty"] - costs
            capital += exit_value - costs
            ret = pnl / entry_value
            trades.append({
                "entry": position["entry"], "exit": exit_price,
                "qty": position["qty"], "pnl": round(pnl, 2),
                "costs": round(costs, 2),
                "return_pct": round(ret * 100, 2),
                "entry_time":     str(position["ts"]),
                "exit_time":      "end-of-period",
                "exit_reason":    "EndOfPeriod",
                "entry_score":    position.get("entry_score"),
                "entry_signals":  position.get("entry_signals", {}),
                "regime_bullish": position.get("regime_bullish"),
            })
            equity_curve.append(capital)

        # -- Compute all metrics -----------------------------------------------
        years   = days / 365
        returns = [t["return_pct"] / 100 for t in trades]
        dd      = Metrics.max_drawdown(equity_curve)
        wl      = Metrics.avg_win_loss(trades)

        # Exit reason breakdown
        exit_reasons = defaultdict(int)
        for t in trades:
            r = t.get("exit_reason", "Unknown")
            if r.startswith("StopLoss"):      exit_reasons["stop_loss"]    += 1
            elif r.startswith("TakeProfit"):  exit_reasons["take_profit"]  += 1
            elif r.startswith("Trailing"):    exit_reasons["trailing_stop"] += 1
            elif r.startswith("Signal"):      exit_reasons["signal"]        += 1
            else:                             exit_reasons["other"]         += 1

        result = {
            "symbol":               symbol,
            "instrument":           instrument,
            "period_days":          days,
            "interval":             interval,
            "candles_used":         len(candles),
            "run_at":               str(datetime.now()),
            "min_score":            min_score,
            "regime_filter":        regime_filter,

            # Core metrics
            "total_trades":         len(trades),
            "win_rate_pct":         Metrics.win_rate(trades),
            "profit_factor":        Metrics.profit_factor(trades),
            "expectancy_rs":        Metrics.expectancy(trades),
            "sharpe_ratio":         Metrics.sharpe(returns),
            "sortino_ratio":        Metrics.sortino(returns),
            "calmar_ratio":         Metrics.calmar(
                                        (capital - self.initial_capital) / self.initial_capital * 100,
                                        dd["pct"], years),

            # Capital
            "initial_capital":      round(self.initial_capital, 2),
            "final_capital":        round(capital, 2),
            "net_pnl":              round(capital - self.initial_capital, 2),
            "net_pnl_pct":          round((capital - self.initial_capital) / self.initial_capital * 100, 2),
            "cagr_pct":             Metrics.cagr(self.initial_capital, capital, years),

            # Drawdown
            "max_drawdown_pct":     dd["pct"],
            "max_drawdown_abs":     dd["abs"],
            "drawdown_recovery_bars": dd["recovery_bars"],

            # Trade analysis
            "avg_win_rs":           wl["avg_win"],
            "avg_loss_rs":          wl["avg_loss"],
            "win_loss_ratio":       wl["ratio"],
            "max_win_rs":           wl["max_win"],
            "max_loss_rs":          wl["max_loss"],
            "streaks":              Metrics.streak(trades),
            "monthly_pnl":          Metrics.monthly_pnl(trades),
            "exit_reasons":         dict(exit_reasons),

            "total_costs_rs":       round(sum(t.get("costs", 0) for t in trades), 2),
            "trades":               trades,
            "equity_curve":         equity_curve[::max(1, len(equity_curve)//200)],
        }

        self._print_report(result)
        self._save(result)
        return result

    # -- Report printer --------------------------------------------------------

    def _print_report(self, m: dict):
        S = "=" * 58
        s = "-" * 58
        print(f"\n{S}")
        print(f"  HISTORICAL BACKTEST — {m['symbol']}  ({m['period_days']}d)")
        print(S)
        print(f"  Capital    : Rs.{m['initial_capital']:>8.2f}  ->  Rs.{m['final_capital']:.2f}")
        print(f"  Net P&L    : Rs.{m['net_pnl']:>+8.2f}  ({m['net_pnl_pct']:+.2f}%)")
        print(f"  CAGR       : {m['cagr_pct']:+.2f}%")
        print(f"  Total Costs: Rs.{m.get('total_costs_rs', 0):.2f}  "
              f"(brokerage+STT+slippage — {m.get('total_costs_rs',0)/m['initial_capital']*100:.1f}% of capital)")
        print(s)
        print(f"  {'Metric':<22} {'Value':>12}   {'Benchmark'}")
        print(s)
        _row = lambda name, val, bench: print(f"  {name:<22} {str(val):>12}   {bench}")
        _row("Total Trades",       m["total_trades"],      ">=10 for reliability")
        _row("Win Rate",           f"{m['win_rate_pct']:.1f}%",    ">=55% = good")
        _row("Profit Factor",      m["profit_factor"],     ">=1.5 = good, >=2.0 = excellent")
        _row("Expectancy (Rs.)",   m["expectancy_rs"],     "> 0 = profitable system")
        _row("Sharpe Ratio",       m["sharpe_ratio"],      ">=1.0 = good, >=2.0 = excellent")
        _row("Sortino Ratio",      m["sortino_ratio"],     ">=1.5 = good (downside-only risk)")
        _row("Calmar Ratio",       m["calmar_ratio"],      ">=1.0 = acceptable, >=3.0 = excellent")
        _row("Max Drawdown",       f"{m['max_drawdown_pct']:.2f}%", "<=10% = well-managed")
        _row("Drawdown Recovery",  f"{m['drawdown_recovery_bars']} bars", "lower = better")
        _row("Avg Win",            f"Rs.{m['avg_win_rs']}", "")
        _row("Avg Loss",           f"Rs.{m['avg_loss_rs']}", "")
        _row("Win/Loss Ratio",     m["win_loss_ratio"],    ">=2.0 = excellent")
        _row("Best Win Streak",    m["streaks"]["best_win_streak"],  "")
        _row("Worst Loss Streak",  m["streaks"]["best_loss_streak"], "keep <=3")
        print(s)
        # Exit reasons
        er = m["exit_reasons"]
        print(f"  Exit Reasons: SL={er.get('stop_loss',0)}  "
              f"TP={er.get('take_profit',0)}  "
              f"Trail={er.get('trailing_stop',0)}  "
              f"Signal={er.get('signal',0)}")
        print(s)
        # Monthly P&L
        if m["monthly_pnl"]:
            print("  Monthly P&L:")
            for month, pnl in m["monthly_pnl"].items():
                bar = "#" * min(20, int(abs(pnl) / 50)) if pnl != 0 else ""
                sign = "+" if pnl >= 0 else ""
                print(f"    {month}  {sign}Rs.{pnl:>7.2f}  {bar}")
        print(s)
        grade, verdict = _grade(m)
        print(f"  Grade: {grade}   Verdict: {verdict}")
        print(S + "\n")

    def _save(self, m: dict):
        fname = RESULTS_DIR / f"{m['symbol']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        fname.write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")
        log.info(f"Saved -> backtest_results/{fname.name}")


# ==============================================================================
#  PAPER TRADER (Forward Testing)
# ==============================================================================

class PaperTrader:
    """
    Simulates live trading with zero real money.
    Runs in parallel with the live bot via tick() calls.
    Full risk management applied — identical to real bot but orders are fake.
    """

    def __init__(self, capital: float = 5000.0):
        self.initial_capital = capital
        self.state           = self._load()
        self.risk            = RiskManager(capital)

    def _load(self) -> dict:
        if FORWARD_STATE_FILE.exists():
            try:
                return json.loads(FORWARD_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "capital":          self.initial_capital,
            "positions":        {},
            "trades":           [],
            "equity_snapshots": [],
            "started_at":       str(datetime.now()),
        }

    def _save(self):
        FORWARD_STATE_FILE.write_text(
            json.dumps(self.state, indent=2, default=str), encoding="utf-8")

    def tick(self, instrument: str, symbol: str, candles: list):
        """Call every 30-min cycle for each stock during market hours."""
        if len(candles) < 50:
            return

        ltp    = candles[-1][4]
        scored = score_signals(candles)
        action = scored["action"]
        score  = scored["score"]

        capital     = self.state["capital"]
        in_position = instrument in self.state["positions"]

        # -- Risk exits --------------------------------------------------------
        if in_position:
            pos    = self.state["positions"][instrument]
            sl     = pos["entry"] * 0.98   # 2% stop loss
            tp     = pos["entry"] * 1.04   # 4% take profit
            pos["high"] = max(pos.get("high", ltp), ltp)
            trail  = pos["high"] * 0.985   # 1.5% trailing stop

            exit_reason = None
            if ltp <= sl:
                exit_reason = f"StopLoss@{sl:.2f}"
            elif ltp >= tp:
                exit_reason = f"TakeProfit@{tp:.2f}"
            elif ltp <= trail and pos["high"] > pos["entry"] * 1.005:
                exit_reason = f"TrailingStop@{trail:.2f}"
            elif action == "SELL" and score >= 0.40:
                exit_reason = f"Signal:SELL"

            if exit_reason:
                self._close(instrument, symbol, ltp, exit_reason)
                in_position = False

        # -- Entry -------------------------------------------------------------
        if not in_position and action == "BUY" and score >= 0.40:
            ok, reason = self.risk.can_trade(self.state["positions"], capital)
            if ok and capital >= ltp:
                stats  = compute_stats(self.state["trades"])
                invest = kelly_position_size(
                    capital, stats["win_rate"], stats["avg_win_pct"],
                    stats["avg_loss_pct"], aggressiveness=0.5)
                invest = max(invest, capital * 0.02)
                qty    = max(1, int(invest / ltp))
                cost   = qty * ltp
                if cost <= capital:
                    self.state["capital"] -= cost
                    self.state["positions"][instrument] = {
                        "symbol": symbol, "qty": qty, "entry": ltp,
                        "high": ltp, "entry_time": str(datetime.now()),
                        "score": score
                    }
                    log.info(f"[PAPER] BUY  {qty}x {symbol} @ Rs.{ltp:.2f}  score={score:.2f}")

        # -- Equity snapshot ---------------------------------------------------
        open_val = sum(
            p["qty"] * ltp if k == instrument else p["qty"] * p["entry"]
            for k, p in self.state["positions"].items()
        )
        self.state["equity_snapshots"].append({
            "t": str(datetime.now()),
            "eq": round(self.state["capital"] + open_val, 2)
        })
        self.state["equity_snapshots"] = self.state["equity_snapshots"][-1000:]
        self._save()

    def _close(self, instrument: str, symbol: str, ltp: float, reason: str):
        pos = self.state["positions"].pop(instrument, None)
        if not pos:
            return
        pnl = (ltp - pos["entry"]) * pos["qty"]
        self.state["capital"] += pos["qty"] * ltp
        ret = pnl / (pos["entry"] * pos["qty"])
        self.state["trades"].append({
            "symbol": symbol, "entry": pos["entry"], "exit": ltp,
            "qty": pos["qty"], "pnl": round(pnl, 2),
            "return_pct": round(ret * 100, 2),
            "entry_time": pos["entry_time"],
            "exit_time":  str(datetime.now()),
            "exit_reason": reason,
        })
        self.risk.record_trade(pnl, symbol)
        sign = "+" if pnl >= 0 else ""
        log.info(f"[PAPER] SELL {symbol} @ Rs.{ltp:.2f}  P&L:{sign}Rs.{pnl:.2f}  [{reason}]")
        self._save()

    def report(self):
        trades = self.state["trades"]
        eq     = [s["eq"] for s in self.state["equity_snapshots"]]
        cap    = self.state["capital"]

        returns = [t["return_pct"] / 100 for t in trades]
        dd      = Metrics.max_drawdown(eq) if len(eq) >= 2 else {"pct": 0, "abs": 0}
        wl      = Metrics.avg_win_loss(trades)

        S = "=" * 58
        s = "-" * 58
        print(f"\n{S}")
        print(f"  PAPER TRADING REPORT  (No Real Money)")
        print(f"  Started: {self.state['started_at'][:16]}")
        print(S)
        print(f"  Capital    : Rs.{self.initial_capital:.2f}  ->  Rs.{cap:.2f}")
        net = cap - self.initial_capital
        print(f"  Net P&L    : Rs.{net:+.2f}  ({net/self.initial_capital*100:+.2f}%)")
        print(s)
        print(f"  Total Trades    : {len(trades)}  |  Open: {len(self.state['positions'])}")
        print(f"  Win Rate        : {Metrics.win_rate(trades):.1f}%")
        print(f"  Profit Factor   : {Metrics.profit_factor(trades)}")
        print(f"  Expectancy      : Rs.{Metrics.expectancy(trades)}")
        print(f"  Sharpe Ratio    : {Metrics.sharpe(returns)}")
        print(f"  Sortino Ratio   : {Metrics.sortino(returns)}")
        print(f"  Max Drawdown    : {dd['pct']:.2f}%  (Rs.{dd['abs']})")
        print(f"  Avg Win / Loss  : Rs.{wl['avg_win']} / Rs.{wl['avg_loss']}  (ratio {wl['ratio']})")
        if self.state["positions"]:
            print(s)
            print("  Open Paper Positions:")
            for inst, p in self.state["positions"].items():
                print(f"    {p['symbol']}  {p['qty']}x @ Rs.{p['entry']:.2f}  "
                      f"(since {p['entry_time'][:16]})")
        if trades:
            print(s)
            print(f"  Last 5 paper trades:")
            for t in trades[-5:]:
                sign = "+" if t["pnl"] >= 0 else ""
                print(f"    {t['exit_time'][:16]}  {t['symbol']:<12}  "
                      f"{sign}Rs.{t['pnl']:>7.2f}  ({sign}{t['return_pct']:.2f}%)  "
                      f"[{t['exit_reason']}]")
        print(S + "\n")


# ==============================================================================
#  GRADER + UNIVERSE RUNNER
# ==============================================================================

def _grade(m: dict) -> tuple:
    pts = 0
    if m["sharpe_ratio"]      >= 1.0: pts += 2
    if m["sharpe_ratio"]      >= 2.0: pts += 1
    if m["sortino_ratio"]     >= 1.5: pts += 1
    if m["win_rate_pct"]      >= 55:  pts += 2
    if m["profit_factor"]     >= 1.5: pts += 2
    if m["profit_factor"]     >= 2.0: pts += 1
    if m["max_drawdown_pct"]  <= 10:  pts += 1
    if m["calmar_ratio"]      >= 1.0: pts += 1
    if m["win_loss_ratio"]    >= 2.0: pts += 1
    if m["total_trades"]      >= 10:  pts += 1
    if m.get("expectancy_rs", 0) > 0: pts += 1

    if   pts >= 11: return "A+", "Exceptional — deploy live with confidence"
    elif pts >=  9: return "A",  "Strong — ready for live trading"
    elif pts >=  7: return "B+", "Good — minor tuning recommended"
    elif pts >=  5: return "B",  "Decent — backtest more periods first"
    elif pts >=  3: return "C",  "Weak — needs significant improvement"
    else:           return "D",  "Poor — do NOT trade live with this"


def run_universe(days: int = 90, capital: float = 5000.0, top_n: int = 15):
    try:
        from stock_universe import get_plain_symbols
        symbols = get_plain_symbols(["LARGE_CAP"])[:top_n]
    except Exception:
        symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                   "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "WIPRO"]

    bt      = Backtester(capital=capital)
    results = []

    for sym in symbols:
        inst = f"NSE_EQ|{sym}"
        try:
            m = bt.run(inst, sym, days=days)
            if "error" not in m:
                results.append(m)
            time.sleep(1.2)
        except Exception as e:
            log.error(f"{sym}: {e}")

    results.sort(key=lambda x: x.get("sharpe_ratio", -99), reverse=True)

    S = "=" * 76
    s = "-" * 76
    print(f"\n{S}")
    print(f"  UNIVERSE BACKTEST — Top {len(results)} stocks ranked by Sharpe Ratio")
    print(S)
    print(f"  {'Symbol':<14} {'Sharpe':>7} {'Sortino':>8} {'WinRate':>8} "
          f"{'PF':>6} {'MaxDD%':>7} {'P&L%':>7} {'Grade'}")
    print(s)
    for r in results:
        grade, _ = _grade(r)
        print(f"  {r['symbol']:<14} {r['sharpe_ratio']:>7.2f} "
              f"{r['sortino_ratio']:>8.2f} {r['win_rate_pct']:>7.1f}% "
              f"{r['profit_factor']:>6.2f} {r['max_drawdown_pct']:>6.1f}% "
              f"{r['net_pnl_pct']:>+6.1f}%  {grade}")
    print(S)
    print(f"\n  Best: {results[0]['symbol']} (Sharpe={results[0]['sharpe_ratio']})" if results else "")
    print()


# ==============================================================================
#  CLI
# ==============================================================================

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MoneyBot Backtester + Paper Trader")
    p.add_argument("--symbol",   default="RELIANCE")
    p.add_argument("--days",     type=int,   default=180)
    p.add_argument("--capital",  type=float, default=5000.0)
    p.add_argument("--interval", default="30minute",
                   choices=["30minute", "1day", "1hour", "15minute"])
    p.add_argument("--all",      action="store_true", help="Backtest top stocks")
    p.add_argument("--top",      type=int, default=15)
    p.add_argument("--forward",  action="store_true", help="Paper trade report")
    p.add_argument("--risk",     action="store_true", help="Risk manager status")
    p.add_argument("--compare",  nargs="+",            help="Compare multiple symbols")
    args = p.parse_args()

    if args.forward:
        PaperTrader(capital=args.capital).report()
    elif args.risk:
        RiskManager(capital=args.capital).print_status()
    elif args.all:
        run_universe(days=args.days, capital=args.capital, top_n=args.top)
    elif args.compare:
        bt = Backtester(capital=args.capital)
        for sym in args.compare:
            bt.run(f"NSE_EQ|{sym}", sym, days=args.days, interval=args.interval)
            time.sleep(1)
    else:
        bt = Backtester(capital=args.capital)
        bt.run(f"NSE_EQ|{args.symbol}", args.symbol,
               days=args.days, interval=args.interval)
