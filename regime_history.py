"""
regime_history.py — Market Regime History tracker.

Appended once per trading day by auto_daily.py.
Produces a human-readable table and a CSV for analysis.

Usage:
  python regime_history.py           # print table
  python regime_history.py --csv     # export to regime_history.csv
"""

import json
import sys
import csv
from datetime import date, datetime
from pathlib import Path

HISTORY_FILE = Path("regime_history.json")
CSV_FILE     = Path("regime_history.csv")


def load() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save(history: list):
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, default=str), encoding="utf-8")


def record(regime: str, pnl_cumulative: float = 0.0,
           nifty: float = 0.0, positions: int = 0):
    """Append one entry for today. Safe to call multiple times — idempotent."""
    history = load()
    today = str(date.today())

    if history and history[-1]["date"] == today:
        # Update today's entry (regime can change intraday in theory)
        history[-1].update({
            "regime": regime,
            "pnl_cumulative": round(pnl_cumulative, 2),
            "nifty": round(nifty, 2),
            "positions": positions,
        })
    else:
        history.append({
            "date": today,
            "regime": regime,
            "pnl_cumulative": round(pnl_cumulative, 2),
            "nifty": round(nifty, 2),
            "positions": positions,
        })

    history = history[-730:]  # keep 2 years
    save(history)


def _build_periods(history: list) -> list:
    """Collapse daily entries into continuous regime periods."""
    if not history:
        return []

    periods = []
    current_regime = history[0]["regime"]
    period_start   = history[0]["date"]
    pnl_start      = history[0]["pnl_cumulative"]
    days            = 1

    for entry in history[1:]:
        if entry["regime"] == current_regime:
            days += 1
        else:
            periods.append({
                "start":  period_start,
                "end":    history[history.index(entry) - 1]["date"],
                "regime": current_regime,
                "days":   days,
                "pnl":    round(entry["pnl_cumulative"] - pnl_start, 2),
            })
            current_regime = entry["regime"]
            period_start   = entry["date"]
            pnl_start      = entry["pnl_cumulative"]
            days            = 1

    # Close the last open period
    periods.append({
        "start":  period_start,
        "end":    history[-1]["date"],
        "regime": current_regime,
        "days":   days,
        "pnl":    round(history[-1]["pnl_cumulative"] - pnl_start, 2),
    })

    return periods


def show():
    history = load()
    if not history:
        print("  No regime history yet. Starts recording on first run day.")
        return

    periods = _build_periods(history)

    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  MARKET REGIME HISTORY — MoneyBot RS60/EP40")
    print(f"  {history[0]['date']} → {history[-1]['date']} "
          f"({len(history)} trading days)")
    print(sep)
    print()
    print(f"  {'Period':<22} {'Regime':<8} {'Days':>5} {'PnL':>12}")
    print(f"  {'─'*55}")

    regime_totals = {"BULL": {"days": 0, "pnl": 0.0},
                     "FLAT": {"days": 0, "pnl": 0.0},
                     "BEAR": {"days": 0, "pnl": 0.0}}

    for p in periods:
        pnl_str = f"Rs.{p['pnl']:+,.0f}"
        print(f"  {p['start']} → {p['end']:<10} "
              f"{p['regime']:<8} {p['days']:>5} {pnl_str:>12}")
        if p["regime"] in regime_totals:
            regime_totals[p["regime"]]["days"] += p["days"]
            regime_totals[p["regime"]]["pnl"]  += p["pnl"]

    total_days = sum(v["days"] for v in regime_totals.values())
    total_pnl  = history[-1]["pnl_cumulative"] if history else 0.0

    print(f"\n  SUMMARY BY REGIME:")
    print(f"  {'Regime':<8} {'Days':>6} {'% Time':>8} {'PnL':>12}")
    print(f"  {'─'*38}")
    for regime in ("BULL", "FLAT", "BEAR"):
        d   = regime_totals[regime]["days"]
        p   = regime_totals[regime]["pnl"]
        pct = 100.0 * d / total_days if total_days > 0 else 0
        print(f"  {regime:<8} {d:>6} {pct:>7.1f}% Rs.{p:>+9,.0f}")

    print(f"  {'─'*38}")
    print(f"  {'TOTAL':<8} {total_days:>6} {'100%':>8} Rs.{total_pnl:>+9,.0f}")
    print(sep)


def export_csv():
    history = load()
    if not history:
        print("No data to export.")
        return

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "regime", "nifty",
                                                "positions", "pnl_cumulative"])
        writer.writeheader()
        writer.writerows(history)
    print(f"Exported {len(history)} rows → {CSV_FILE}")


if __name__ == "__main__":
    if "--csv" in sys.argv:
        export_csv()
    else:
        show()
