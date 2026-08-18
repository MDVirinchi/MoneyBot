"""
daily_comparison.py — Production vs Shadow strategy daily comparison.

Reads production state (execution_state.json) and shadow state (shadow_state.json),
plus today's shadow summary passed in, and writes a human-readable comparison to
comparison_log.json.

Run automatically by auto_daily.py Step 6. Can also run standalone:
  python daily_comparison.py
"""

import json
import csv
import sys
from datetime import date, datetime
from pathlib import Path

COMPARISON_LOG  = Path("comparison_log.json")
PROD_STATE_FILE = Path("execution_state.json")
SHAD_STATE_FILE = Path("shadow_state.json")
PROD_JOURNAL    = Path("trade_journal.csv")
SHAD_JOURNAL    = Path("shadow_journal.csv")

try:
    import config as _cfg
    CAPITAL = getattr(_cfg, "TRADING_CAPITAL_INR", 5_000)
except Exception:
    CAPITAL = 5_000


def _load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _journal_stats(path):
    if not path.exists():
        return {"trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0, "win_rate": 0.0}
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        pass
    trades = len(rows)
    wins   = sum(1 for r in rows if float(r.get("net_pnl", 0) or 0) > 0)
    losses = sum(1 for r in rows if float(r.get("net_pnl", 0) or 0) < 0)
    total  = sum(float(r.get("net_pnl", 0) or 0) for r in rows)
    wr     = round(wins / trades * 100, 1) if trades else 0.0
    return {"trades": trades, "wins": wins, "losses": losses,
            "total_pnl": round(total, 2), "win_rate": wr}


def run_comparison(shadow_summary: dict | None = None):
    today = str(date.today())

    prod_state  = _load_json(PROD_STATE_FILE)
    shad_state  = _load_json(SHAD_STATE_FILE)
    prod_stats  = _journal_stats(PROD_JOURNAL)
    shad_stats  = _journal_stats(SHAD_JOURNAL)

    prod_positions = prod_state.get("positions", {})
    shad_positions = shad_state.get("positions", {})

    prod_invested = sum(p.get("entry", 0) * p.get("qty", 0) for p in prod_positions.values())
    prod_pv = prod_state.get("cash", float(CAPITAL)) + prod_invested
    if "cash" not in prod_state and not prod_positions:
        prod_pv = float(CAPITAL)

    shad_pv = shad_state.get("cash", float(CAPITAL)) + sum(
        p.get("entry", 0) * p.get("qty", 0) for p in shad_positions.values()
    )

    prod_return = round((prod_pv - CAPITAL) / CAPITAL * 100, 2)
    shad_return = round((shad_pv - CAPITAL) / CAPITAL * 100, 2)

    report = {
        "date":     today,
        "capital":  CAPITAL,
        "production": {
            "regime":          prod_state.get("last_regime", "UNKNOWN"),
            "open_positions":  len(prod_positions),
            "portfolio_value": round(prod_pv, 2),
            "total_pnl":       round(prod_state.get("pnl", 0), 2),
            "return_pct":      prod_return,
            **prod_stats,
        },
        "shadow": {
            "regime":          shadow_summary.get("shadow_regime", shad_state.get("last_regime", "UNKNOWN")) if shadow_summary else "UNKNOWN",
            "open_positions":  len(shad_positions),
            "portfolio_value": round(shad_pv, 2),
            "total_pnl":       round(shad_state.get("pnl", 0), 2),
            "return_pct":      shad_return,
            **shad_stats,
        },
        "delta": {
            "return_pct":      round(shad_return - prod_return, 2),
            "pnl":             round(shad_state.get("pnl", 0) - prod_state.get("pnl", 0), 2),
            "win_rate":        round(shad_stats["win_rate"] - prod_stats["win_rate"], 1),
            "trades":          shad_stats["trades"] - prod_stats["trades"],
        },
        "verdict": "",
    }

    delta_ret = report["delta"]["return_pct"]
    if delta_ret > 2:
        report["verdict"] = "SHADOW OUTPERFORMING — monitor for 30+ days before considering promotion"
    elif delta_ret < -2:
        report["verdict"] = "PRODUCTION OUTPERFORMING — shadow regime filter too aggressive"
    else:
        report["verdict"] = "SIMILAR PERFORMANCE — more data needed"

    history = []
    if COMPARISON_LOG.exists():
        try:
            history = json.loads(COMPARISON_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    history.append(report)
    history = history[-90:]
    COMPARISON_LOG.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")

    _print_report(report)
    return report


def _print_report(r):
    p = r["production"]
    s = r["shadow"]
    d = r["delta"]
    sep = "=" * 65

    print(f"\n{sep}")
    print(f"  PRODUCTION vs SHADOW — {r['date']}")
    print(sep)
    print(f"  {'Metric':<22} {'Production':>15} {'Shadow':>15} {'Delta':>10}")
    print(f"  {'-'*62}")

    def row(label, pk, sk, fmt="{}", sign=False):
        pv = p.get(pk, 0)
        sv = s.get(sk or pk, 0)
        dv = d.get(pk.replace("_pct","_pct") if pk in d else sk or pk, "")
        pf = f"Rs.{pv:,.2f}" if "pnl" in pk or "value" in pk else (f"{pv:+.2f}%" if "pct" in pk else str(pv))
        sf = f"Rs.{sv:,.2f}" if "pnl" in pk or "value" in pk else (f"{sv:+.2f}%" if "pct" in pk else str(sv))
        df = f"{dv:+.2f}%" if "pct" in pk and isinstance(dv, (int, float)) else (f"Rs.{dv:+,.2f}" if "pnl" in pk and isinstance(dv, (int,float)) else str(dv) if dv != "" else "-")
        print(f"  {label:<22} {pf:>15} {sf:>15} {df:>10}")

    print(f"  {'Regime':<22} {p.get('regime','?'):>15} {s.get('regime','?'):>15} {'':>10}")
    print(f"  {'Open positions':<22} {p['open_positions']:>15} {s['open_positions']:>15} {s['open_positions']-p['open_positions']:>+10}")
    print(f"  {'Portfolio value':<22} Rs.{p['portfolio_value']:>12,.2f} Rs.{s['portfolio_value']:>12,.2f} Rs.{d['pnl']:>+8,.2f}")
    print(f"  {'Total PnL':<22} Rs.{p['total_pnl']:>12,.2f} Rs.{s['total_pnl']:>12,.2f} Rs.{d['pnl']:>+8,.2f}")
    print(f"  {'Return':<22} {p['return_pct']:>+14.2f}% {s['return_pct']:>+14.2f}% {d['return_pct']:>+9.2f}%")
    print(f"  {'Total trades':<22} {p['trades']:>15} {s['trades']:>15} {d['trades']:>+10}")
    print(f"  {'Win rate':<22} {p['win_rate']:>14.1f}% {s['win_rate']:>14.1f}% {d['win_rate']:>+9.1f}%")
    print(f"\n  Verdict: {r['verdict']}")
    print(f"\n  History saved to {COMPARISON_LOG}")
    print(sep)


def show_history(days=7):
    if not COMPARISON_LOG.exists():
        print("No comparison history found. Run auto_daily.py to generate one.")
        return
    history = json.loads(COMPARISON_LOG.read_text(encoding="utf-8"))
    recent = history[-days:]
    sep = "=" * 75
    print(f"\n{sep}")
    print(f"  COMPARISON HISTORY — Last {len(recent)} days")
    print(sep)
    print(f"  {'Date':<12} {'P.Regime':<10} {'S.Regime':<10} {'P.Return':>10} {'S.Return':>10} {'Delta':>8} {'Verdict'}")
    print(f"  {'-'*73}")
    for r in recent:
        p = r["production"]
        s = r["shadow"]
        d = r["delta"]
        print(f"  {r['date']:<12} {p.get('regime','?'):<10} {s.get('regime','?'):<10} "
              f"{p['return_pct']:>+9.2f}% {s['return_pct']:>+9.2f}% {d['return_pct']:>+7.2f}% "
              f"  {r.get('verdict','')[:35]}")
    print(sep)


if __name__ == "__main__":
    if "--history" in sys.argv:
        show_history()
    else:
        run_comparison()
