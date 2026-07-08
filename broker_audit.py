"""
broker_audit.py — Daily broker-vs-local position audit.
Run daily (or add to Task Scheduler alongside daily_ops_report.py).

Compares trading_state.json against Upstox get_portfolio() and logs
every difference to broker_audit_log.json. Designed to catch drift
before it compounds.

Usage:
  python broker_audit.py            (run audit, print report)
  python broker_audit.py --history  (show last 7 days of audit results)
"""

import json
import sys
import logging
from datetime import datetime, date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AUDIT] %(message)s",
    handlers=[
        logging.FileHandler("broker_audit.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

STATE_FILE = Path("execution_state.json")
AUDIT_LOG = Path("broker_audit_log.json")


def load_local_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"positions": {}, "trades": [], "pnl": 0}


def load_broker_positions():
    """Fetch live positions from Upstox."""
    try:
        import config
        import requests
        headers = {
            "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}",
            "Accept": "application/json"
        }
        r = requests.get(
            "https://api.upstox.com/v2/portfolio/short-term-positions",
            headers=headers, timeout=10
        )
        data = r.json()
        if data.get("status") == "success":
            return data.get("data", [])
        else:
            log.warning(f"Broker API returned: {data.get('status', 'unknown')}")
            return None
    except Exception as e:
        log.warning(f"Broker API failed: {e}")
        return None


def load_audit_history():
    if AUDIT_LOG.exists():
        try:
            return json.loads(AUDIT_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_audit_history(history):
    history = history[-90:]
    AUDIT_LOG.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def run_audit():
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  BROKER AUDIT REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(sep)

    local = load_local_state()
    broker_raw = load_broker_positions()

    local_positions = local.get("positions", {})
    local_map = {}
    for inst, pos in local_positions.items():
        sym = pos.get("plain", inst.split("|")[-1])
        local_map[inst] = {
            "symbol": sym,
            "qty": pos.get("qty", 0),
            "entry": pos.get("entry", 0),
            "pending_sell": pos.get("pending_sell", False),
        }

    if broker_raw is None:
        print("\n  WARNING: Could not fetch broker positions.")
        print("  Possible causes: expired token, API outage, network error.")
        print("  Audit SKIPPED — no comparison possible.\n")

        audit_entry = {
            "date": str(date.today()),
            "time": str(datetime.now()),
            "status": "SKIPPED",
            "reason": "broker API unavailable",
            "local_count": len(local_map),
            "broker_count": None,
            "mismatches": [],
        }
        history = load_audit_history()
        history.append(audit_entry)
        save_audit_history(history)
        return

    broker_map = {}
    for p in broker_raw:
        inst = p.get("instrument_token", "")
        if inst:
            broker_map[inst] = {
                "symbol": inst.split("|")[-1],
                "qty": int(p.get("quantity", 0)),
                "avg_price": float(p.get("average_price", 0)),
            }

    all_instruments = set(list(local_map.keys()) + list(broker_map.keys()))
    mismatches = []

    print(f"\n  Local positions:  {len(local_map)}")
    print(f"  Broker positions: {len(broker_map)}")
    print()

    if not all_instruments:
        print("  Both local and broker are empty. No positions to compare.")
    else:
        print(f"  {'Symbol':<14} {'Local Qty':>10} {'Broker Qty':>11} {'Local Entry':>12} {'Broker Avg':>11} {'Status':<20}")
        print(f"  {'-'*58}")

        for inst in sorted(all_instruments):
            l = local_map.get(inst, {})
            b = broker_map.get(inst, {})
            sym = l.get("symbol") or b.get("symbol", inst.split("|")[-1])
            l_qty = l.get("qty", 0)
            b_qty = b.get("qty", 0)
            l_entry = l.get("entry", 0)
            b_avg = b.get("avg_price", 0)
            pending = l.get("pending_sell", False)

            status = "OK"
            mismatch_type = None

            if inst in local_map and inst not in broker_map:
                if pending:
                    status = "PENDING SELL"
                    mismatch_type = "pending_sell_local_only"
                else:
                    status = "PHANTOM (local only)"
                    mismatch_type = "phantom"
            elif inst not in local_map and inst in broker_map:
                status = "BROKER ONLY"
                mismatch_type = "broker_only"
            elif l_qty != b_qty:
                if b_qty > l_qty and b_qty % l_qty == 0:
                    ratio = b_qty // l_qty
                    status = f"CORPORATE ACTION? (qty x{ratio})"
                    mismatch_type = "corporate_action"
                else:
                    status = f"QTY MISMATCH"
                    mismatch_type = "qty_mismatch"
            elif abs(l_entry - b_avg) > 0.01 * l_entry and l_entry > 0:
                if b_avg > 0 and l_entry / b_avg > 1.5:
                    status = f"CORPORATE ACTION? (price halved)"
                    mismatch_type = "corporate_action"
                else:
                    status = "PRICE DRIFT"
                    mismatch_type = "price_drift"

            if mismatch_type:
                mismatches.append({
                    "instrument": inst, "symbol": sym,
                    "type": mismatch_type,
                    "local_qty": l_qty, "broker_qty": b_qty,
                    "local_entry": round(l_entry, 2),
                    "broker_avg": round(b_avg, 2),
                })

            l_qty_str = str(l_qty) if inst in local_map else "-"
            b_qty_str = str(b_qty) if inst in broker_map else "-"
            l_entry_str = f"Rs.{l_entry:,.2f}" if l_entry else "-"
            b_avg_str = f"Rs.{b_avg:,.2f}" if b_avg else "-"

            color_marker = "***" if mismatch_type else "   "
            print(f"  {sym:<14} {l_qty_str:>10} {b_qty_str:>11} {l_entry_str:>12} {b_avg_str:>11} {color_marker}{status}")

    # Corporate action detection — freeze affected symbols
    corp_actions = [m for m in mismatches if m["type"] == "corporate_action"]
    if corp_actions:
        print(f"\n  *** CORPORATE ACTION DETECTED — FREEZING SYMBOLS ***")
        frozen_file = Path("frozen_symbols.json")
        frozen = []
        if frozen_file.exists():
            try:
                frozen = json.loads(frozen_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        for ca in corp_actions:
            print(f"    {ca['symbol']}: local_qty={ca['local_qty']} broker_qty={ca['broker_qty']} "
                  f"local_entry={ca['local_entry']} broker_avg={ca['broker_avg']}")
            if ca["instrument"] not in [f["instrument"] for f in frozen]:
                frozen.append({
                    "instrument": ca["instrument"],
                    "symbol": ca["symbol"],
                    "reason": "corporate_action",
                    "detected": str(datetime.now()),
                    "local_qty": ca["local_qty"],
                    "broker_qty": ca["broker_qty"],
                })
        frozen_file.write_text(json.dumps(frozen, indent=2, default=str), encoding="utf-8")
        print(f"  {len(frozen)} symbol(s) frozen in frozen_symbols.json")
        print(f"  To unfreeze: delete the entry from frozen_symbols.json after manual review.")
        try:
            from notify import send
            send(f"CORPORATE ACTION DETECTED\n"
                 f"{', '.join(ca['symbol'] for ca in corp_actions)}\n"
                 f"Symbols FROZEN — no buys/sells until manual review")
        except Exception:
            pass

    print()
    if mismatches:
        print(f"  *** {len(mismatches)} MISMATCH(ES) FOUND ***")
        for m in mismatches:
            print(f"    {m['symbol']}: {m['type']} — local_qty={m['local_qty']}, broker_qty={m['broker_qty']}")
    else:
        print(f"  All positions match. No drift detected.")

    audit_entry = {
        "date": str(date.today()),
        "time": str(datetime.now()),
        "status": "CLEAN" if not mismatches else "MISMATCHES",
        "local_count": len(local_map),
        "broker_count": len(broker_map),
        "mismatches": mismatches,
        "local_pnl": round(local.get("pnl", 0), 2),
    }

    history = load_audit_history()
    history.append(audit_entry)
    save_audit_history(history)

    print(f"\n  Audit saved to {AUDIT_LOG}")
    print(sep)


def show_history():
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  BROKER AUDIT HISTORY — Last 7 days")
    print(sep)

    history = load_audit_history()
    if not history:
        print("  No audit history found. Run: python broker_audit.py")
        return

    recent = history[-7:]
    print(f"\n  {'Date':<12} {'Time':<6} {'Status':<12} {'Local':>6} {'Broker':>7} {'Mismatches':>11} {'PnL':>10}")
    print(f"  {'-'*60}")
    for entry in recent:
        t = entry.get("time", "")[:5]
        b = entry.get("broker_count")
        b_str = str(b) if b is not None else "N/A"
        n_mis = len(entry.get("mismatches", []))
        print(f"  {entry['date']:<12} {t:<6} {entry['status']:<12} "
              f"{entry['local_count']:>6} {b_str:>7} {n_mis:>11} "
              f"Rs.{entry.get('local_pnl', 0):>8,.0f}")

    clean = sum(1 for e in recent if e.get("status") == "CLEAN")
    print(f"\n  Clean audits: {clean}/{len(recent)} in last 7 days")
    print(sep)


if __name__ == "__main__":
    if "--history" in sys.argv:
        show_history()
    else:
        run_audit()
