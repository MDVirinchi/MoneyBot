# MoneyBot RS60/EP40 — Release Checklist

Version: check against `LIVE_OPERATIONS.md` for current version.
Complete every item before the first trade of any new release.
A single ❌ in CRITICAL sections blocks the release.

---

## Section 1 — Code (run the morning of deployment)

- [ ] `python test_critical_bugs.py` → **37/37 PASS**
- [ ] `python verify_unit_tests.py` → all PASS
- [ ] `python test_sl_pipeline.py` → all PASS
- [ ] `python invariant_checker.py --strict` → exit code 0
- [ ] No uncommitted edits to `execution_engine.py`, `daily_ops_report.py`, `shadow_engine.py`

If any test fails → **STOP. Do not deploy.**

---

## Section 2 — Strategy (verify before every rebalance cycle)

- [ ] `W_RS = 0.60`, `W_EP = 0.40` unchanged in `daily_ops_report.py`
- [ ] `SL_PCT = 0.10` unchanged in both `daily_ops_report.py` and `execution_engine.py`
- [ ] `TOP_N = 10`, `RS_WINDOW = 63` unchanged
- [ ] REBALANCE_EVERY unchanged (10 trading days)
- [ ] `PAPER_START_DATE` is correct in `daily_ops_report.py`
- [ ] STOCKS universe unchanged (no additions/removals)

If any strategy parameter changed unintentionally → **STOP. Investigate.**

---

## Section 3 — Operations (run before 9:00 AM)

- [ ] `config.py` updated with today's `UPSTOX_ACCESS_TOKEN`
- [ ] Token has not expired — verify by running:
  `python -c "import config; print(len(config.UPSTOX_ACCESS_TOKEN), 'chars')"` → should be > 100 chars
- [ ] Telegram alert test: `python -c "from notify import send; send('MoneyBot: pre-market check OK')"` → message received on phone
- [ ] Internet connection working: `ping 8.8.8.8`
- [ ] Disk space: at least 500 MB free in `C:\Users\rushi\Downloads\moneybot\`
- [ ] Today is a weekday AND not an NSE holiday (check NSE_HOLIDAYS_2026 in invariant_checker.py)
- [ ] Clock is synchronized: check system tray clock matches IST from phone

---

## Section 4 — Safety (run before 9:00 AM)

- [ ] `python invariant_checker.py` → **ALL INVARIANTS HOLD**
- [ ] `python broker_audit.py` → **CLEAN** (no mismatches from yesterday)
- [ ] `execution_state.json` is readable and valid:
  `python -c "import json; s=json.load(open('execution_state.json')); print('positions:', len(s.get('positions',{})))"` → no error
- [ ] State backup created:
  `copy execution_state.json execution_state.backup_%date:~-4,4%%date:~-7,2%%date:~-10,2%.json`
- [ ] No `INVARIANT_VIOLATION_*.json` files from previous sessions (if present: investigate before trading)
- [ ] `execution_engine.lock` is not held by a zombie process:
  `python -c "from pathlib import Path; f=open('execution_engine.lock','w'); import msvcrt; msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1); print('Lock free'); f.close()"` → should print "Lock free"

---

## Section 5 — Post-Market Verification (run after 4:00 PM)

- [ ] `python broker_audit.py` → **CLEAN**
- [ ] `python broker_audit.py --history` → last 5 days all CLEAN or SKIPPED
- [ ] `python invariant_checker.py` → **ALL INVARIANTS HOLD**
- [ ] `trade_journal.csv` has entries for today's closed trades
- [ ] `auto_daily.log` shows no CRITICAL or ERROR lines for today
- [ ] Compare paper PnL in `execution_state.json` with shadow_state.json — both directionally consistent

---

## Sign-off

Date: _______________
Checklist completed by: _______________
Invariant check result: _______________
Broker audit result: _______________
Approved to trade: YES / NO
