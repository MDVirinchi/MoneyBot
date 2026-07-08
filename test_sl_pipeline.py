"""
test_sl_pipeline.py — End-to-end paper test of the SL monitoring and broker audit pipeline.

What this tests:
  1. Inject a synthetic paper position into execution_state.json
  2. Simulate an LTP below the stop-loss level (mocked — no real Upstox call)
  3. Verify monitor_stop_losses() fires the sell path
  4. Verify execution_state.json is updated (position removed, trade logged)
  5. Verify trade_journal.csv receives the record
  6. Verify broker_audit sees a PHANTOM (expected: local had it, broker never did)
  7. Restore execution_state.json to its original state

No real orders are placed. No strategy logic is touched.
"""

import json
import shutil
import sys
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []

def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}{' — ' + detail if detail else ''}")

sep = "=" * 65
print(f"\n{sep}")
print(f"  SL PIPELINE TEST — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(sep)

STATE_FILE = Path("execution_state.json")
JOURNAL_FILE = Path("trade_journal.csv")
BACKUP = Path("execution_state.backup.json")

# ── 1. BACKUP existing state ─────────────────────────────────────────────────
print("\n[1] Setup")
original_state = None
if STATE_FILE.exists():
    shutil.copy(STATE_FILE, BACKUP)
    original_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    print(f"  Backed up existing state ({len(original_state.get('positions', {}))} positions)")
else:
    print("  No existing state file — will create fresh")

journal_lines_before = 0
if JOURNAL_FILE.exists():
    journal_lines_before = sum(1 for _ in open(JOURNAL_FILE, encoding="utf-8"))

# ── 2. INJECT synthetic position ─────────────────────────────────────────────
print("\n[2] Injecting synthetic paper position")

FAKE_INSTRUMENT = "NSE_EQ|TESTSTOCK"
FAKE_SYMBOL     = "TESTSTOCK"
FAKE_ENTRY      = 1000.00
FAKE_SL         = 900.00   # 10% below entry
FAKE_QTY        = 1
FAKE_ENTRY_DATE = str(date.today() - timedelta(days=3))  # bought 3 days ago

synthetic_state = {
    "positions": {
        FAKE_INSTRUMENT: {
            "qty":      FAKE_QTY,
            "entry":    FAKE_ENTRY,
            "sl_price": FAKE_SL,
            "plain":    FAKE_SYMBOL,
            "time":     f"{FAKE_ENTRY_DATE}T09:15:00",
            "order_id": "PAPER_TEST_001",
        }
    },
    "trades":        original_state["trades"] if original_state else [],
    "pnl":           original_state["pnl"] if original_state else 0,
    "last_ops_date": original_state.get("last_ops_date", "") if original_state else "",
}

STATE_FILE.write_text(json.dumps(synthetic_state, indent=2), encoding="utf-8")
loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
check("Synthetic position written to execution_state.json",
      FAKE_INSTRUMENT in loaded["positions"])
check("Entry price correct", loaded["positions"][FAKE_INSTRUMENT]["entry"] == FAKE_ENTRY)
check("SL price correct",    loaded["positions"][FAKE_INSTRUMENT]["sl_price"] == FAKE_SL)

# ── 3. MOCK LTP below SL and call monitor_stop_losses ────────────────────────
print("\n[3] Simulating LTP below stop-loss")

FAKE_LTP = 850.00  # below SL of 900 → should trigger exit
print(f"  Entry price : Rs.{FAKE_ENTRY:,.2f}")
print(f"  Stop-loss   : Rs.{FAKE_SL:,.2f}")
print(f"  Simulated LTP: Rs.{FAKE_LTP:,.2f}  << below SL, should trigger")

import execution_engine

# Mock the UpstoxClient so no real API calls are made
mock_client = MagicMock()
mock_client.get_ltp.return_value = {
    FAKE_INSTRUMENT: {"last_price": FAKE_LTP}
}
# Mock place_order to simulate a confirmed fill at the LTP
mock_client.place_order.return_value = {
    "status":         "success",
    "fill_confirmed": True,
    "fill_price":     FAKE_LTP,
    "fill_qty":       FAKE_QTY,
    "order_id":       "PAPER_TEST_EXIT_001",
}

state = execution_engine.load_state()
check("State loaded with synthetic position",
      FAKE_INSTRUMENT in state["positions"])

exits = execution_engine.monitor_stop_losses(mock_client, state)

check("monitor_stop_losses detected SL breach",
      len(exits) > 0,
      f"exits={exits}")
check("get_ltp was called once",
      mock_client.get_ltp.called)
check("place_order was called (sell fired)",
      mock_client.place_order.called)

if mock_client.place_order.called:
    call_args = mock_client.place_order.call_args
    check("Sell order was for correct instrument",
          call_args[0][0] == FAKE_INSTRUMENT)
    check("Sell order was SELL side",
          call_args[0][2] == "SELL")
    check("Sell quantity matches",
          call_args[0][1] == FAKE_QTY)

# ── 4. VERIFY state updated ──────────────────────────────────────────────────
print("\n[4] Verifying state after SL exit")

updated = execution_engine.load_state()
check("Position removed from execution_state.json",
      FAKE_INSTRUMENT not in updated["positions"])

expected_pnl = (FAKE_LTP - FAKE_ENTRY) * FAKE_QTY
check("PnL recorded in state",
      abs(updated["pnl"] - (original_state["pnl"] if original_state else 0) - expected_pnl) < 1.0,
      f"pnl delta={updated['pnl'] - (original_state['pnl'] if original_state else 0):.2f}, expected={expected_pnl:.2f}")

# ── 5. VERIFY trade journal ──────────────────────────────────────────────────
print("\n[5] Verifying trade journal")

journal_lines_after = 0
if JOURNAL_FILE.exists():
    journal_lines_after = sum(1 for _ in open(JOURNAL_FILE, encoding="utf-8"))

check("Trade journal received new entry",
      journal_lines_after > journal_lines_before,
      f"before={journal_lines_before}, after={journal_lines_after}")

if JOURNAL_FILE.exists() and journal_lines_after > journal_lines_before:
    import csv
    rows = list(csv.DictReader(open(JOURNAL_FILE, encoding="utf-8")))
    last = rows[-1] if rows else {}
    check("Journal entry has correct symbol",   last.get("symbol") == FAKE_SYMBOL)
    check("Journal entry has correct exit_reason", "Stop Loss" in last.get("exit_reason", ""))
    check("Journal holding_days > 0",           int(last.get("holding_days", 0)) > 0,
          f"holding_days={last.get('holding_days')}")

# ── 6. VERIFY broker audit sees PHANTOM ─────────────────────────────────────
print("\n[6] Verifying broker audit reconciliation")
print("  (Expected: PHANTOM for synthetic position — broker never had it)")

# Re-inject the position so we can test audit against it
STATE_FILE.write_text(json.dumps(synthetic_state, indent=2), encoding="utf-8")

import broker_audit
mock_broker_positions = []  # broker has nothing (paper trade — no real order placed)

with patch.object(broker_audit, "load_broker_positions", return_value=mock_broker_positions):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        broker_audit.run_audit()
    audit_output = buf.getvalue()

check("Broker audit ran without crashing", True)
check("Broker audit detected PHANTOM position",
      "PHANTOM" in audit_output,
      "Expected PHANTOM for paper position not in broker")
check("Broker audit shows 1 local position",
      "Local positions:  1" in audit_output,
      audit_output[:300])
check("Broker audit shows 0 broker positions",
      "Broker positions: 0" in audit_output)

# ── 7. RESTORE original state ────────────────────────────────────────────────
print("\n[7] Restoring original state")

if BACKUP.exists():
    shutil.copy(BACKUP, STATE_FILE)
    BACKUP.unlink()
    print("  Restored execution_state.json from backup")
elif original_state is None:
    STATE_FILE.unlink(missing_ok=True)
    print("  Removed test state file (none existed before)")

restored = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {"positions": {}}
check("Synthetic position gone after restore",
      FAKE_INSTRUMENT not in restored["positions"])

# ── RESULTS ──────────────────────────────────────────────────────────────────
print(f"\n{sep}")
print(f"  RESULTS: {len(PASS)} PASS / {len(FAIL)} FAIL")
if FAIL:
    print(f"\n  FAILED checks:")
    for f in FAIL:
        print(f"    FAIL: {f}")
else:
    print(f"\n  All checks passed. SL pipeline is operational.")
print(sep)

sys.exit(0 if not FAIL else 1)
