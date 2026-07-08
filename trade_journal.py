"""
trade_journal.py — Automatic trade journal for every completed trade.
Records to trade_journal.csv so 6 months from now you can answer
"where did the profits actually come from?" without rerunning backtests.

Every trade records:
  entry_date, exit_date, holding_days, symbol, side,
  entry_price, exit_price, qty, gross_pnl, costs, net_pnl,
  exit_reason, signal_score, regime_at_entry, regime_at_exit,
  strategy_version, slippage_actual

Usage:
  # Record a trade (called by trading_bot.py automatically):
  from trade_journal import record_trade
  record_trade(symbol="RELIANCE", entry_date="2026-06-20", ...)

  # View journal:
  python trade_journal.py                (last 20 trades)
  python trade_journal.py --summary      (aggregate stats)
  python trade_journal.py --by-reason    (PnL by exit reason)
  python trade_journal.py --by-symbol    (PnL by symbol)
"""

import csv
import sys
import io
import statistics
from datetime import datetime, date
from pathlib import Path
from collections import defaultdict

JOURNAL_FILE = Path("trade_journal.csv")
STRATEGY_VERSION = "v2.0"  # RS60/EP40 + Policy C + 50DMA

FIELDS = [
    "trade_id", "entry_date", "exit_date", "holding_days",
    "symbol", "instrument", "side",
    "entry_price", "exit_price", "qty",
    "gross_pnl", "costs", "net_pnl", "return_pct",
    "exit_reason", "signal_score",
    "regime_at_entry", "regime_at_exit",
    "strategy_version", "system",
    "order_id_entry", "order_id_exit",
    "notes",
]


def _ensure_header():
    if not JOURNAL_FILE.exists():
        with open(JOURNAL_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()


def _next_id():
    if not JOURNAL_FILE.exists():
        return 1
    with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
        return max(1, sum(1 for _ in f) - 1)  # subtract header row


def record_trade(
    symbol: str,
    instrument: str = "",
    entry_date: str = "",
    exit_date: str = "",
    holding_days: int = 0,
    entry_price: float = 0,
    exit_price: float = 0,
    qty: int = 0,
    gross_pnl: float = 0,
    costs: float = 0,
    net_pnl: float = 0,
    return_pct: float = 0,
    exit_reason: str = "",
    signal_score: float = 0,
    regime_at_entry: str = "",
    regime_at_exit: str = "",
    system: str = "B",
    order_id_entry: str = "",
    order_id_exit: str = "",
    notes: str = "",
):
    """Append one trade to the journal CSV."""
    _ensure_header()

    if not exit_date:
        exit_date = str(date.today())
    if not entry_date:
        entry_date = exit_date

    if net_pnl == 0 and gross_pnl != 0:
        net_pnl = gross_pnl - costs
    if return_pct == 0 and entry_price > 0 and qty > 0:
        return_pct = round(net_pnl / (entry_price * qty) * 100, 4)

    row = {
        "trade_id": _next_id(),
        "entry_date": entry_date,
        "exit_date": exit_date,
        "holding_days": holding_days,
        "symbol": symbol,
        "instrument": instrument,
        "side": "ROUND_TRIP",
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "qty": qty,
        "gross_pnl": round(gross_pnl, 2),
        "costs": round(costs, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(return_pct, 4),
        "exit_reason": exit_reason,
        "signal_score": round(signal_score, 3),
        "regime_at_entry": regime_at_entry,
        "regime_at_exit": regime_at_exit,
        "strategy_version": STRATEGY_VERSION,
        "system": system,
        "order_id_entry": order_id_entry,
        "order_id_exit": order_id_exit,
        "notes": notes,
    }

    with open(JOURNAL_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerow(row)

    return row


def load_journal():
    if not JOURNAL_FILE.exists():
        return []
    with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            for num_field in ["entry_price", "exit_price", "gross_pnl", "costs",
                              "net_pnl", "return_pct", "signal_score"]:
                try:
                    r[num_field] = float(r.get(num_field, 0) or 0)
                except (ValueError, TypeError):
                    r[num_field] = 0.0
            for int_field in ["qty", "holding_days", "trade_id"]:
                try:
                    r[int_field] = int(float(r.get(int_field, 0) or 0))
                except (ValueError, TypeError):
                    r[int_field] = 0
            rows.append(r)
        return rows


def print_recent(n=20):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    trades = load_journal()
    sep = "=" * 95
    print(f"\n{sep}")
    print(f"  TRADE JOURNAL — Last {min(n, len(trades))} of {len(trades)} trades")
    print(sep)

    if not trades:
        print("  No trades recorded yet.")
        print(f"  Journal file: {JOURNAL_FILE.absolute()}")
        return

    print(f"  {'ID':>4} {'Date':>10} {'Symbol':<12} {'Entry':>8} {'Exit':>8} {'Qty':>4} "
          f"{'Net PnL':>10} {'Ret%':>7} {'Exit Reason':<18} {'Hold':>4}")
    print(f"  {'-'*90}")

    for t in trades[-n:]:
        print(f"  {t['trade_id']:>4} {t['exit_date']:>10} {t['symbol']:<12} "
              f"{t['entry_price']:>8.2f} {t['exit_price']:>8.2f} {t['qty']:>4} "
              f"{t['net_pnl']:>+10.2f} {t['return_pct']:>+6.2f}% {t['exit_reason']:<18} "
              f"{t['holding_days']:>4}d")

    total_pnl = sum(t["net_pnl"] for t in trades)
    wins = sum(1 for t in trades if t["net_pnl"] > 0)
    print(f"\n  Total PnL: Rs.{total_pnl:+,.2f}  |  Win rate: {wins}/{len(trades)} "
          f"({wins/len(trades)*100:.1f}%)")
    print(sep)


def print_summary():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    trades = load_journal()
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  TRADE JOURNAL SUMMARY — {len(trades)} trades")
    print(sep)

    if len(trades) < 2:
        print("  Not enough trades for summary.")
        return

    pnls = [t["net_pnl"] for t in trades]
    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    holding = [t["holding_days"] for t in trades if t["holding_days"] > 0]

    print(f"  Total trades:     {len(trades)}")
    print(f"  Total PnL:        Rs.{sum(pnls):+,.2f}")
    print(f"  Win rate:         {len(wins)}/{len(trades)} ({len(wins)/len(trades)*100:.1f}%)")
    print(f"  Avg win:          Rs.{statistics.mean([t['net_pnl'] for t in wins]):+,.2f}" if wins else "")
    print(f"  Avg loss:         Rs.{statistics.mean([t['net_pnl'] for t in losses]):+,.2f}" if losses else "")
    print(f"  Avg holding days: {statistics.mean(holding):.1f}" if holding else "")
    print(f"  Best trade:       Rs.{max(pnls):+,.2f}")
    print(f"  Worst trade:      Rs.{min(pnls):+,.2f}")
    print(sep)


def print_by_reason():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    trades = load_journal()
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  PnL BY EXIT REASON")
    print(sep)

    by_reason = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
    for t in trades:
        r = t.get("exit_reason", "Unknown")
        if r.startswith("Stop Loss") or r == "SL": r = "Stop Loss"
        elif r.startswith("Take Profit"): r = "Take Profit"
        elif r.startswith("Trailing"): r = "Trailing Stop"
        elif r.startswith("Signal"): r = "Signal"
        elif r.startswith("Regime") or r.startswith("RISK EXIT"): r = "Regime/Risk"
        by_reason[r]["count"] += 1
        by_reason[r]["pnl"] += t["net_pnl"]
        if t["net_pnl"] > 0:
            by_reason[r]["wins"] += 1

    print(f"  {'Reason':<20} {'Count':>6} {'Total PnL':>12} {'Avg PnL':>10} {'Win%':>6}")
    print(f"  {'-'*56}")
    for reason, data in sorted(by_reason.items(), key=lambda x: -x[1]["pnl"]):
        wr = data["wins"] / data["count"] * 100 if data["count"] else 0
        print(f"  {reason:<20} {data['count']:>6} {data['pnl']:>+12,.2f} "
              f"{data['pnl']/data['count']:>+10,.2f} {wr:>5.1f}%")
    print(sep)


def print_by_symbol():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    trades = load_journal()
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  PnL BY SYMBOL (top 15)")
    print(sep)

    by_sym = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
    for t in trades:
        s = t.get("symbol", "?")
        by_sym[s]["count"] += 1
        by_sym[s]["pnl"] += t["net_pnl"]
        if t["net_pnl"] > 0:
            by_sym[s]["wins"] += 1

    sorted_syms = sorted(by_sym.items(), key=lambda x: -x[1]["pnl"])
    print(f"  {'Symbol':<14} {'Trades':>6} {'Total PnL':>12} {'Avg PnL':>10} {'Win%':>6}")
    print(f"  {'-'*50}")
    for sym, data in sorted_syms[:15]:
        wr = data["wins"] / data["count"] * 100 if data["count"] else 0
        print(f"  {sym:<14} {data['count']:>6} {data['pnl']:>+12,.2f} "
              f"{data['pnl']/data['count']:>+10,.2f} {wr:>5.1f}%")
    print(sep)


if __name__ == "__main__":
    if "--summary" in sys.argv:
        print_summary()
    elif "--by-reason" in sys.argv:
        print_by_reason()
    elif "--by-symbol" in sys.argv:
        print_by_symbol()
    else:
        print_recent()
