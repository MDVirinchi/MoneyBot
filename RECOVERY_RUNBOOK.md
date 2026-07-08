# MoneyBot RS60/EP40 — Recovery Runbook

Use this document when something goes wrong during trading hours.
Each scenario tells you exactly what to check and what to do.
Time matters — work through steps in order, don't skip.

---

## SCENARIO 1: Bot didn't run this morning

**Symptoms:** No entries in `auto_daily.log` for today. No trades placed.

**Steps:**
1. Check Task Scheduler: `taskschd.msc` → find MoneyBot task → check last run time and result code.
2. If result code is non-zero: `type auto_daily.log` and look for ERROR near today's date.
3. Run manually: `cd C:\Users\rushi\Downloads\moneybot && python auto_daily.py --dry-run`
4. If dry-run succeeds, run for real: `python auto_daily.py`
5. If it's past 9:30 AM: orders at market open are missed. SL monitor still needed:
   `python execution_engine.py --monitor`

**Do NOT run twice.** The single-instance lock will block the second run, but confirm with:
`python invariant_checker.py` before running manually.

---

## SCENARIO 2: Token expired / Upstox login failed

**Symptoms:** `auto_daily.log` shows `401` or `token expired`. No orders placed.

**Steps:**
1. Log in to Upstox app → generate new access token.
2. Open `config.py` and update `UPSTOX_ACCESS_TOKEN = "NEW_TOKEN_HERE"`.
3. Verify: `python -c "import config; print('Token OK:', len(config.UPSTOX_ACCESS_TOKEN) > 100)"`
4. If it's before 9:30 AM: re-run `python auto_daily.py`
5. If it's after 9:30 AM but positions are open: run only the SL monitor:
   `python execution_engine.py --monitor`
6. The token hot-reloads on every API call — no restart needed once config.py is saved.

**Open positions are at risk without SL monitoring.** Prioritize getting the monitor running.

---

## SCENARIO 3: Broker audit shows PHANTOM position

**Symptoms:** `broker_audit.py` output shows `PHANTOM (local only)` for a symbol.

**This means:** Local state says you own stock X, but broker shows nothing.

**Steps:**
1. First, do NOT panic-edit the state file.
2. Check if a SELL order was placed today for this symbol:
   `python broker_audit.py --history` — look for the symbol in recent mismatches.
3. Log in to Upstox web and manually check your positions for that symbol.
4. **If broker truly has 0 shares** (sell completed but state not updated):
   - Edit `execution_state.json` manually, remove the phantom position.
   - Record the trade in `trade_journal.csv` manually if it's not there.
5. **If broker shows the position** (audit data was stale): rerun `python broker_audit.py`.
6. After any manual edit, run `python invariant_checker.py` to verify state is clean.

---

## SCENARIO 4: Broker audit shows BROKER ONLY position

**Symptoms:** `broker_audit.py` shows a stock in broker that local state doesn't know about.

**This means:** Either (a) a manual trade was placed, or (b) a buy order completed but state wasn't saved.

**Steps:**
1. Check `execution_engine.log` for today — did a buy order for this symbol fire?
2. If YES (buy fired, state not saved due to crash):
   - Add the position to `execution_state.json` manually with entry price from the broker fill.
   - Set `sl_price = fill_price * 0.90`.
3. If NO (manual trade): decide whether to track it. If not tracking, sell it manually via Upstox.
4. Run `python invariant_checker.py` after any edits.

---

## SCENARIO 5: Duplicate order suspected

**Symptoms:** Two orders for the same stock on the same day visible in Upstox order book.

**Steps:**
1. **Do not sell anything yet.** Check your actual net position first.
2. Log in to Upstox → Portfolio → check actual qty for the stock.
3. If you have DOUBLE the expected qty (e.g., 2 shares when 1 was intended):
   - Sell the extra shares manually via Upstox app.
   - This creates a "broker only" entry which broker_audit will flag — that's fine.
4. If you have a SHORT position (negative qty): this is the Bug #3 scenario (now fixed).
   - Close the short immediately via Upstox app.
   - Contact Upstox support if there are penalty charges.
5. After correcting: run `python invariant_checker.py` to verify state.

---

## SCENARIO 6: execution_state.json appears corrupted or empty

**Symptoms:** Bot starts but shows 0 positions when you know you have open positions.
OR: `python -c "import json; json.load(open('execution_state.json'))"` raises JSONDecodeError.

**Steps:**
1. Check for backup: `dir execution_state.backup_*.json` — use the most recent.
2. Restore: `copy execution_state.backup_YYYYMMDD.json execution_state.json`
3. Verify: `python invariant_checker.py`
4. If no backup exists: reconstruct from broker positions:
   - `python broker_audit.py` will show broker positions.
   - Manually build `execution_state.json` using broker entry prices.
5. After restore: re-run `python execution_engine.py --monitor` to resume SL protection.

---

## SCENARIO 7: Windows rebooted during trading hours

**Symptoms:** Auto_daily.py stopped mid-execution. Positions may be open without SL monitoring.

**Steps:**
1. Check what completed: `type auto_daily.log | findstr "STEP\|FAILED\|SUCCESS"`
2. Check if orders were placed: `type execution_engine.log | findstr "BOUGHT\|SOLD\|FAILED"`
3. Run `python broker_audit.py` to compare local state vs broker.
4. Fix any mismatches (see scenarios 3, 4 above).
5. Restart SL monitor immediately (most important): `python execution_engine.py --monitor`
6. After market close (3:30 PM), run `python broker_audit.py` again for post-market reconciliation.

---

## SCENARIO 8: Internet dropped during order placement

**Symptoms:** `execution_engine.log` shows timeout errors. Unclear if orders were placed.

**Steps:**
1. When connection restores: check `python broker_audit.py` immediately.
2. For each position in broker that's not in local state → BROKER ONLY scenario (see #4).
3. For each position in local state not in broker → PHANTOM scenario (see #3).
4. The already_ordered_today() duplicate protection will block re-orders for anything already placed.
5. Run SL monitor once connectivity is restored: `python execution_engine.py --monitor`

---

## SCENARIO 9: Invariant check finds CRITICAL violation

**Symptoms:** `python invariant_checker.py` outputs `*** HALT TRADING ***`
AND a `INVARIANT_VIOLATION_YYYYMMDD_HHMMSS.json` snapshot file is created.

**Steps:**
1. Do NOT start the bot. Do NOT run execute_today.
2. Read the violation file: `type INVARIANT_VIOLATION_*.json`
3. The most common CRITICAL violations and their fixes:
   - `SL_BELOW_ENTRY`: SL price is above entry. Edit the position in execution_state.json manually.
   - `POSITION_QTY_POSITIVE`: qty is 0 or negative. Either fix qty or remove the position.
   - `NO_NAN_VALUES`: a price field is NaN. Find and fix the corrupt value.
   - `BEAR_MEANS_CASH`: in BEAR regime but positions open. Run execute_today to trigger regime exit.
4. After fixing: `python invariant_checker.py` must show ALL INVARIANTS HOLD before trading.

---

## SCENARIO 10: Corporate action detected (symbol frozen)

**Symptoms:** `broker_audit.py` shows `CORPORATE ACTION? (qty x2)`. Symbol added to `frozen_symbols.json`.

**Steps:**
1. Verify the corporate action via NSE website or Upstox corporate actions page.
2. If it's a genuine split/bonus: the local state position needs updating.
   - For 2:1 split: double the qty in execution_state.json, halve the entry price.
   - Recalculate sl_price = new_entry * 0.90.
3. Remove the symbol from `frozen_symbols.json` after updating state.
4. Run `python invariant_checker.py` to verify.
5. Run `python broker_audit.py` to confirm reconciled.

---

## EMERGENCY STOP (halt all trading immediately)

If you need to stop the bot and prevent any new orders:

```
1. Kill the Python process:
   taskkill /F /IM python.exe

2. Verify no lock held:
   del execution_engine.lock   (safe to delete — it's a lock guard, not state)

3. Verify state is intact:
   python invariant_checker.py

4. To prevent auto-restart:
   Task Scheduler → disable MoneyBot task

5. To resume later:
   Re-enable Task Scheduler task
   Update config.py with fresh token
   Run RELEASE_CHECKLIST.md before restarting
```

---

## Key file locations

| File | Purpose |
|------|---------|
| `execution_state.json` | Current positions and PnL |
| `execution_state.backup_*.json` | Pre-run backups |
| `trade_journal.csv` | All completed trades |
| `auto_daily.log` | Daily run log |
| `execution_engine.log` | Order placement log |
| `broker_audit_log.json` | Last 90 days of reconciliation |
| `frozen_symbols.json` | Corporate-action-frozen symbols |
| `INVARIANT_VIOLATION_*.json` | State snapshot on critical failure |
| `ops_log_YYYY-MM-DD.json` | Today's signals and regime |
