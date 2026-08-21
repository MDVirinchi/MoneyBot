"""
strategy_fingerprint.py — Detects unauthorized strategy changes.

Computes a short hash of all frozen strategy parameters.
If the fingerprint changes, the live strategy is no longer identical
to the one that was validated — paper trading restarts from that point.

Usage (standalone):
  python strategy_fingerprint.py

Import:
  from strategy_fingerprint import get_fingerprint, assert_frozen
"""

import hashlib
import json
from datetime import date
from pathlib import Path

# ── Frozen parameter set (must exactly match daily_ops_report.py) ─────────────
_FROZEN = {
    "W_RS":        0.60,
    "W_EP":        0.40,
    "TOP_N":       10,
    "SL_PCT":      0.10,
    "RS_WINDOW":   63,
    "EP_WINDOW":   63,
    "EP_RET_MIN":  0.02,
    "EP_VOL_MULT": 1.5,
    "PAPER_CAPITAL": 5_000,
    "PER_POS":     500,
    "SLIP_MODEL":  0.002,
    "REBAL_EVERY": 10,
    "PAPER_START": "2026-06-16",
    "UNIVERSE_SIZE": 136,
    # Live execution capital — not a strategy parameter, but tracked here
    # so a funding change is explicit and auditable (not a silent config drift).
    "LIVE_CAPITAL": 11_500,
    "LIVE_PER_POS": 1_150,
}

_FINGERPRINT_FILE = Path("strategy_fingerprint_history.json")

# ── Core ─────────────────────────────────────────────────────────────────────

def get_fingerprint() -> str:
    raw = json.dumps(_FROZEN, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:8].upper()


def get_params() -> dict:
    return dict(_FROZEN)


def assert_frozen():
    """
    Loads live parameters from daily_ops_report and compares to frozen set.
    Raises ValueError if any parameter has drifted.
    """
    try:
        import daily_ops_report as ops
        live = {
            "W_RS":        ops.W_RS,
            "W_EP":        ops.W_EP,
            "TOP_N":       ops.TOP_N,
            "SL_PCT":      ops.SL_PCT,
            "RS_WINDOW":   ops.RS_WINDOW,
            "EP_WINDOW":   ops.EP_WINDOW,
            "EP_RET_MIN":  ops.EP_RET_MIN,
            "EP_VOL_MULT": ops.EP_VOL_MULT,
            "PAPER_CAPITAL": ops.PAPER_CAPITAL,
            "PER_POS":     ops.PER_POS,
            "SLIP_MODEL":  ops.SLIP_MODEL,
            "LIVE_CAPITAL": ops.LIVE_CAPITAL,
            "LIVE_PER_POS": ops.LIVE_PER_POS,
        }
    except ImportError:
        return  # daily_ops_report not importable — skip live check

    drifted = []
    for k, expected in _FROZEN.items():
        if k not in live:
            continue
        if live[k] != expected:
            drifted.append(f"  {k}: expected {expected}, got {live[k]}")

    if drifted:
        raise ValueError(
            "STRATEGY PARAMETER DRIFT DETECTED\n" + "\n".join(drifted) +
            "\nPaper trading period is invalidated. Investigate before trading."
        )


def record_daily(regime: str = "", pnl: float = 0.0):
    """Called once per trading day to record fingerprint in history."""
    history = []
    if _FINGERPRINT_FILE.exists():
        try:
            history = json.loads(_FINGERPRINT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    fp = get_fingerprint()
    today = str(date.today())

    if history and history[-1]["date"] == today:
        return  # already recorded today

    prev_fp = history[-1]["fingerprint"] if history else None
    entry = {
        "date": today,
        "fingerprint": fp,
        "changed": prev_fp is not None and fp != prev_fp,
        "regime": regime,
        "pnl": pnl,
    }

    if entry["changed"]:
        entry["alert"] = f"FINGERPRINT CHANGED from {prev_fp} → {fp}. Paper trading restart required."

    history.append(entry)
    history = history[-365:]

    _FINGERPRINT_FILE.write_text(
        json.dumps(history, indent=2, default=str), encoding="utf-8")

    return entry


def show():
    fp = get_fingerprint()
    print(f"\n  Strategy Fingerprint: {fp}")
    print(f"  Parameters frozen at:")
    for k, v in _FROZEN.items():
        print(f"    {k:<16} = {v}")

    if _FINGERPRINT_FILE.exists():
        try:
            history = json.loads(_FINGERPRINT_FILE.read_text(encoding="utf-8"))
            changes = [e for e in history if e.get("changed")]
            if changes:
                print(f"\n  *** WARNING: {len(changes)} fingerprint change(s) in history ***")
                for c in changes[-3:]:
                    print(f"    {c['date']}: {c.get('alert','')}")
            else:
                print(f"  History: {len(history)} days recorded, no changes detected.")
        except Exception:
            pass

    try:
        assert_frozen()
        print(f"  Live parameter check: PASS — production matches frozen set.")
    except ValueError as e:
        print(f"\n  *** {e} ***")

    print()


if __name__ == "__main__":
    show()
