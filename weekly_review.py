"""
weekly_review.py — MoneyBot Weekly Engineering Review.

Generates a concise report covering:
  - Code health (uncommitted changes, test results)
  - Paper trading results (trades, win rate, PnL)
  - Operational health (broker incidents, invariant violations, recovery events)
  - Shadow vs production comparison
  - Strategy fingerprint stability
  - Recommended action

Run every weekend (or any time):
  python weekly_review.py
  python weekly_review.py --days 30   (last 30 days)
"""

import json
import sys
import os
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DAYS = 7


def _days_arg() -> int:
    for arg in sys.argv[1:]:
        if arg.startswith("--days"):
            try:
                return int(arg.split("=")[-1]) if "=" in arg else int(sys.argv[sys.argv.index(arg) + 1])
            except (IndexError, ValueError):
                pass
    return DEFAULT_DAYS


def _load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else []


def _cutoff(days: int) -> date:
    return date.today() - timedelta(days=days)


# ── Code health ───────────────────────────────────────────────────────────────

def _git_stats(days: int) -> dict:
    cutoff = datetime.now() - timedelta(days=days)
    result = {"commits": 0, "files_changed": 0, "uncommitted": False, "branch": "master"}

    try:
        since = cutoff.strftime("%Y-%m-%d")
        log = subprocess.run(
            ["git", "log", f"--since={since}", "--oneline"],
            capture_output=True, text=True, timeout=10)
        result["commits"] = len([l for l in log.stdout.splitlines() if l.strip()])

        stat = subprocess.run(
            ["git", "log", f"--since={since}", "--stat", "--format="],
            capture_output=True, text=True, timeout=10)
        changed = set()
        for line in stat.stdout.splitlines():
            if "|" in line and not line.strip().startswith("Bin"):
                changed.add(line.split("|")[0].strip())
        result["files_changed"] = len(changed)

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10)
        result["uncommitted"] = bool(status.stdout.strip())

        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=10)
        result["branch"] = branch.stdout.strip() or "master"
    except Exception:
        pass

    return result


# ── Trading results ───────────────────────────────────────────────────────────

def _trade_stats(days: int) -> dict:
    cutoff = _cutoff(days)
    journal = Path("trade_journal.csv")
    stats = {"trades": 0, "wins": 0, "losses": 0, "win_rate": None,
             "pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0}

    if not journal.exists():
        return stats

    try:
        import csv
        wins, losses, win_pnls, loss_pnls = [], [], [], []
        with open(journal, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    d = date.fromisoformat(row.get("date", "")[:10])
                except ValueError:
                    continue
                if d < cutoff:
                    continue
                pnl = float(row.get("pnl", 0))
                stats["pnl"] += pnl
                stats["trades"] += 1
                if pnl > 0:
                    wins.append(pnl)
                else:
                    losses.append(pnl)

        stats["wins"]   = len(wins)
        stats["losses"] = len(losses)
        if stats["trades"] > 0:
            stats["win_rate"] = 100.0 * stats["wins"] / stats["trades"]
        stats["avg_win"]  = sum(wins) / len(wins) if wins else 0.0
        stats["avg_loss"] = sum(losses) / len(losses) if losses else 0.0
    except Exception:
        pass

    return stats


# ── Operational health ────────────────────────────────────────────────────────

def _ops_health(days: int) -> dict:
    cutoff = _cutoff(days)
    health = {
        "broker_incidents": 0,
        "invariant_violations": 0,
        "recovery_events": 0,
        "days_ran": 0,
        "days_skipped": 0,
    }

    # Broker audit incidents
    audit_history = _load_json(Path("broker_audit_log.json"))
    for entry in audit_history:
        try:
            d = date.fromisoformat(str(entry.get("date", ""))[:10])
        except ValueError:
            continue
        if d < cutoff:
            continue
        if entry.get("status") == "MISMATCHES":
            health["broker_incidents"] += len(entry.get("mismatches", []))

    # Invariant violation snapshots
    for f in Path(".").glob("INVARIANT_VIOLATION_*.json"):
        try:
            ts = f.stem.replace("INVARIANT_VIOLATION_", "")
            d = date.fromisoformat(ts[:10].replace("_", "-") if "_" in ts[:10] else ts[:10])
            if d >= cutoff:
                health["invariant_violations"] += 1
        except Exception:
            continue

    # Daily summary: count days ran vs skipped
    summaries = _load_json(Path("daily_summary.json"))
    for s in summaries:
        try:
            d = date.fromisoformat(str(s.get("date", ""))[:10])
        except ValueError:
            continue
        if d < cutoff:
            continue
        if s.get("status") in ("WEEKEND", "HOLIDAY"):
            health["days_skipped"] += 1
        else:
            health["days_ran"] += 1
        if s.get("errors", 0) > 0:
            health["recovery_events"] += 1

    return health


# ── Confidence (today) ────────────────────────────────────────────────────────

def _current_confidence() -> float:
    try:
        from daily_explain import confidence_score
        return confidence_score()["overall"]
    except Exception:
        return 0.0


# ── Shadow vs production ──────────────────────────────────────────────────────

def _shadow_delta() -> dict:
    state = _load_json(Path("execution_state.json"), {})
    shadow = _load_json(Path("shadow_state.json"), {})
    prod_pnl   = state.get("pnl", None)
    shadow_pnl = shadow.get("pnl", None)
    if prod_pnl is None or shadow_pnl is None:
        return {"prod_pnl": None, "shadow_pnl": None, "delta": None}
    return {
        "prod_pnl":   round(prod_pnl, 2),
        "shadow_pnl": round(shadow_pnl, 2),
        "delta":      round(shadow_pnl - prod_pnl, 2),
    }


# ── Strategy fingerprint ──────────────────────────────────────────────────────

def _fingerprint_status() -> dict:
    try:
        from strategy_fingerprint import get_fingerprint, _FINGERPRINT_FILE
        import json as _j
        fp = get_fingerprint()
        changes = 0
        if _FINGERPRINT_FILE.exists():
            history = _j.loads(_FINGERPRINT_FILE.read_text(encoding="utf-8"))
            cutoff  = _cutoff(DEFAULT_DAYS)
            changes = sum(1 for e in history
                         if e.get("changed") and
                         date.fromisoformat(e["date"][:10]) >= cutoff)
        return {"fingerprint": fp, "changes": changes}
    except Exception:
        return {"fingerprint": "UNAVAILABLE", "changes": 0}


# ── Recommendation ────────────────────────────────────────────────────────────

def _recommend(trade: dict, health: dict, fp: dict, confidence: float) -> str:
    issues = []
    if fp["changes"] > 0:
        issues.append(f"Strategy fingerprint changed {fp['changes']} time(s) — investigate before trading.")
    if health["broker_incidents"] > 0:
        issues.append(f"{health['broker_incidents']} broker incident(s) — review audit log.")
    if health["invariant_violations"] > 0:
        issues.append(f"{health['invariant_violations']} invariant violation(s) — read INVARIANT_VIOLATION_*.json.")
    if health["recovery_events"] > 0:
        issues.append(f"{health['recovery_events']} error day(s) — check auto_daily.log.")
    if confidence > 0 and confidence < 80:
        issues.append(f"Confidence score is {confidence:.0f}% — below safe-to-trade threshold.")

    if issues:
        return "ACTION REQUIRED:\n" + "\n".join(f"  • {i}" for i in issues)

    if trade["trades"] == 0:
        return "No trades this period. Continue observation."
    if trade["win_rate"] is not None and trade["win_rate"] < 40:
        return "Win rate below 40% — document and observe. Do NOT adjust strategy yet."

    return "No changes. Continue observation."


# ── Main ──────────────────────────────────────────────────────────────────────

def generate(days: int = DEFAULT_DAYS):
    sep = "=" * 65

    git   = _git_stats(days)
    trade = _trade_stats(days)
    ops   = _ops_health(days)
    shadow = _shadow_delta()
    fp    = _fingerprint_status()
    conf  = _current_confidence()
    rec   = _recommend(trade, ops, fp, conf)

    print(f"\n{sep}")
    print(f"  MONEYBOT WEEKLY ENGINEERING REVIEW")
    print(f"  Period: last {days} days  ({_cutoff(days)} → {date.today()})")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(sep)

    # Code
    print(f"\n  CODE")
    print(f"  Commits this period:   {git['commits']}")
    print(f"  Files changed:         {git['files_changed']}")
    print(f"  Branch:                {git['branch']}")
    print(f"  Uncommitted edits:     {'YES ⚠' if git['uncommitted'] else 'None'}")
    print(f"  Strategy fingerprint:  {fp['fingerprint']}")
    print(f"  Fingerprint changes:   {fp['changes']}" + (" ⚠" if fp["changes"] > 0 else ""))

    # Trades
    print(f"\n  PAPER TRADES (last {days} days)")
    if trade["trades"] == 0:
        print(f"  No closed trades this period.")
    else:
        wr = f"{trade['win_rate']:.1f}%" if trade["win_rate"] is not None else "n/a"
        print(f"  Closed trades:         {trade['trades']}")
        print(f"  Wins:                  {trade['wins']}")
        print(f"  Losses:                {trade['losses']}")
        print(f"  Win Rate:              {wr}")
        print(f"  PnL (period):          Rs.{trade['pnl']:+,.0f}")
        if trade["avg_win"]:
            print(f"  Avg Win:               Rs.{trade['avg_win']:+,.0f}")
        if trade["avg_loss"]:
            print(f"  Avg Loss:              Rs.{trade['avg_loss']:+,.0f}")

    # Ops health
    print(f"\n  OPERATIONAL HEALTH")
    print(f"  Days bot ran:          {ops['days_ran']}")
    print(f"  Days skipped:          {ops['days_skipped']}")
    print(f"  Broker incidents:      {ops['broker_incidents']}" + (" ⚠" if ops["broker_incidents"] else ""))
    print(f"  Invariant violations:  {ops['invariant_violations']}" + (" ⚠" if ops["invariant_violations"] else ""))
    print(f"  Recovery events:       {ops['recovery_events']}" + (" ⚠" if ops["recovery_events"] else ""))

    # Shadow
    print(f"\n  SHADOW vs PRODUCTION (cumulative, all-time)")
    if shadow["prod_pnl"] is None:
        print(f"  No state data available.")
    else:
        print(f"  Production PnL:        Rs.{shadow['prod_pnl']:+,.0f}")
        print(f"  Shadow PnL:            Rs.{shadow['shadow_pnl']:+,.0f}")
        delta = shadow["delta"]
        flag = "  ← large divergence, investigate" if abs(delta) > 500 else ""
        print(f"  Delta (shadow - prod): Rs.{delta:+,.0f}{flag}")

    # Confidence
    if conf > 0:
        verdict = "SAFE TO TRADE" if conf >= 80 else "DO NOT TRADE"
        print(f"\n  CONFIDENCE (today):    {conf:.1f}%  →  {verdict}")

    # Recommendation
    print(f"\n  RECOMMENDED ACTION:")
    for line in rec.splitlines():
        print(f"  {line}")

    print(sep)


if __name__ == "__main__":
    generate(_days_arg())
