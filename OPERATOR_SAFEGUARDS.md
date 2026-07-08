# MoneyBot — Human Error Audit & Operator Safeguards

The question: "Assume the operator (me) makes mistakes. What breaks?"

Every incident below is realistic. The safeguard column says what exists now
or what should be added to prevent the mistake from reaching a trade.

---

## Operator mistake #1: Runs the bot twice manually

**How it happens:** You run `python auto_daily.py` at 9:08 AM.
You're not sure it started, so you run it again at 9:10 AM.

**What breaks:** Two execute_today() calls race to place orders.

**Current safeguard:** `msvcrt.locking()` in `acquire_lock()` blocks the second instance.
The second run logs "Another instance is already running" and exits.
✅ **PROTECTED.**

---

## Operator mistake #2: Updates the wrong config.py

**How it happens:** You have two Python projects open. You paste the new token
into the wrong config.py (a different project).

**What breaks:** Bot runs with yesterday's expired token. All API calls return 401.

**Current safeguard:** pre_market_health_check() calls get_funds() and fails on 401.
No trades are placed if the health check fails.
✅ **PROTECTED** — but you won't get an alert explaining WHY it failed.

**Recommended addition:** `python invariant_checker.py` at startup now checks the token
format (JWT structure). A token from yesterday is structurally valid, so the format
check won't catch it — only the live API call will.
**Better detection:** Add a token expiry check by decoding the JWT payload:

```python
import base64, json as _json
def _token_expiry(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        data = _json.loads(base64.b64decode(payload))
        return data.get("exp", 0)
    except Exception:
        return 0
```

If `_token_expiry(token) < time.time()`: the token is already expired.
Add this to `invariant_checker.py` System invariant SY1.

---

## Operator mistake #3: Forgets to renew the token

**How it happens:** Token expires overnight. Operator is busy or traveling.
Bot runs at 9:05 AM with stale token.

**What breaks:** Health check fails → no trades → positions open with no SL monitoring.

**Current safeguard:** None before 9:00 AM.

**Recommended addition:** A separate evening reminder at 8:00 PM (before sleep):

```
Schedule a new task in Task Scheduler:
  Name:    MoneyBot Token Reminder
  Time:    8:00 PM daily
  Command: python -c "from notify import send; send('MoneyBot: Update Upstox token before 9 AM tomorrow')"
```

This is a 5-minute setup. Prevents the most common operational failure.

---

## Operator mistake #4: Starts the bot on a public holiday

**How it happens:** Republic Day (Jan 26) is a Monday. Operator doesn't check the calendar.

**What breaks:** Bot runs, downloads data (stale from Friday), attempts to place orders.
Upstox rejects orders with "Exchange is closed." No fills. SL monitor runs but LTP API
returns stale data or errors.

**Current safeguard:** `invariant_checker.py` now warns on NSE holidays (HIGH severity, not CRITICAL).
Daily_ops_report staleness check will catch if Nifty data is > 5 days old.

**Gap:** The holiday check in invariant_checker is HIGH, not CRITICAL — it won't halt.
**Recommended addition:** Change `NSE_HOLIDAY_CHECK` to CRITICAL severity, or add to the
RELEASE_CHECKLIST.md as an explicit check. The operator should always confirm the date.

---

## Operator mistake #5: Edits execution_state.json manually and makes a typo

**How it happens:** During reconciliation (scenario 3 or 4 from runbook), operator
edits the state JSON and accidentally puts `"qty": "3"` (string) instead of `"qty": 3` (int).

**What breaks:** `pos["qty"]` in execute_sells() becomes a string.
`(exit_price - pos["entry"]) * exit_qty` where exit_qty is `"3"` →
`TypeError: can't multiply sequence by non-int` → sell crashes.

**Current safeguard:** None.

**Recommended addition:** invariant_checker.py `check_state_invariants()` now checks
that each field is a valid type. But it doesn't check string-vs-int specifically.
**Add to `_check_value()`:**
```python
if path in ("qty",) and isinstance(value, str):
    report.add("FIELD_TYPE_CORRECT", HIGH,
               f"{path}={value!r} is a string, should be int")
```

**Also:** After any manual JSON edit, always run `python invariant_checker.py` before
allowing trading. This is now in the RELEASE_CHECKLIST.

---

## Operator mistake #6: Deploys the wrong version of a file

**How it happens:** You were testing a change to execution_engine.py.
You accidentally save the test version instead of reverting to production.

**What breaks:** Depends on what changed. Could be anything.

**Current safeguard:** None. No version control (not a git repo).

**Recommended addition:** Before running, check the file's modification time:
```
dir execution_engine.py /T:W
```
If it was modified today, be certain you know why.

**Stronger safeguard:** Initialize a git repo in the moneybot folder.
`git init && git add -A && git commit -m "MoneyBot v1.0.0"`
Then any accidental edit shows up as a diff: `git diff`
This is the single highest-value process improvement available.

---

## Operator mistake #7: Runs auto_daily.py on a non-trading account (wrong Upstox login)

**How it happens:** You have two Upstox accounts (main + test). The token in config.py
belongs to the test account. The bot places real orders in what you thought was paper trading.

**What breaks:** Real orders placed in real account with Rs.500 allocations.

**Current safeguard:** `TRADING_CAPITAL_INR = 5000` limits position size to Rs.500.
Financial impact of a wrong-account run: up to Rs.5,000 in real orders.
(This is the paper trading safety net — small capital limits damage from any mistake.)

**Recommended addition:**
1. Always add a comment to config.py: `# ACCOUNT: PAPER (replace with LIVE when ready)`
2. Add `ACCOUNT_TYPE = "PAPER"` to config.py and print it in the startup banner.
3. Print the Upstox client_id from the decoded JWT at startup so you can verify the account.

---

## Operator mistake #8: Accidentally deletes execution_state.json

**How it happens:** Cleaning up files, accidentally `del execution_state.json`.

**What breaks:** Bot starts with 0 positions. In BULL regime with rebalance_due:
bot tries to buy new positions without knowing old ones exist at the broker.

**Current safeguard:** `already_ordered_today()` would block duplicate buys IF the positions
were bought today and orders are still in the order book. But if this happens after market
hours or the next day, the protection is gone.

**Recovery:** Reconstruct state from broker positions (Runbook Scenario 4).

**Recommended addition:** The RELEASE_CHECKLIST now includes a daily backup step.
`copy execution_state.json execution_state.backup_YYYYMMDD.json` before running.
Consider automating this backup as the FIRST step in auto_daily.py.

---

## Operator mistake #9: Changes a strategy parameter thinking it won't matter

**How it happens:** "Let me just change TOP_N from 10 to 8 to reduce exposure."

**What breaks:**
- RS/EP percentile rankings are recalculated for a different set.
- If 2 current positions fall out of the new Top-8, they get sold immediately.
- The paper trading data no longer reflects the backtest strategy.
- The paper vs live comparison is invalidated.

**Current safeguard:** The RELEASE_CHECKLIST section 2 verifies all parameters explicitly.
The docstring in daily_ops_report.py says "STRATEGY FROZEN."

**Recommended addition:** Add a hash check of strategy parameters at startup:
```python
import hashlib
_STRATEGY_FINGERPRINT = hashlib.md5(
    f"{W_RS}{W_EP}{TOP_N}{SL_PCT}{RS_WINDOW}".encode()
).hexdigest()[:8]
# If this changes, you changed the strategy. Paper trading restarts.
```
Print the fingerprint in every ops report header. If it ever changes unexpectedly,
you know immediately.

---

## Operator mistake #10: Reads broker_audit output wrong and concludes no problem

**How it happens:** `python broker_audit.py` shows "1 MISMATCH FOUND" but operator
sees "CLEAN audits: 6/7 in last 7 days" and assumes it's fine.

**What breaks:** The one mismatch today is a PHANTOM — a position the bot thinks it has
but the broker sold (maybe a corporate action forced-sell). Operator doesn't act.
Bot tries to sell this PHANTOM position tomorrow → broker rejects → logged as FAILED.

**Current safeguard:** The PHANTOM mismatch type is highlighted with *** in the output.

**Recommended addition:** Any PHANTOM or BROKER_ONLY mismatch should send a Telegram alert.
Currently: `broker_audit.py` only sends Telegram on corporate actions, not on PHANTOM.
**Add to `run_audit()` before saving history:**
```python
phantoms = [m for m in mismatches if m["type"] == "phantom"]
if phantoms:
    try:
        from notify import send
        send(f"PHANTOM POSITION DETECTED\n"
             f"{', '.join(m['symbol'] for m in phantoms)}\n"
             f"Bot thinks it owns these — broker doesn't. Manual review needed.")
    except Exception:
        pass
```

---

## Summary: Safeguards by status

| Mistake | Protected now? | Action needed |
|---------|---------------|---------------|
| Run twice | ✅ File lock | None |
| Wrong config.py | ✅ Health check fails | Add JWT expiry decode |
| Forget token renewal | ❌ | Add 8 PM Telegram reminder |
| Trade on holiday | ⚠️ HIGH warning only | Upgrade to CRITICAL |
| Manual JSON typo | ⚠️ Invariant catches most | Add string-vs-int check |
| Wrong file version | ❌ | Initialize git repo |
| Wrong Upstox account | ⚠️ Small capital limits damage | Add account-type label |
| Delete state file | ⚠️ Manual recovery only | Automate daily backup |
| Change strategy param | ⚠️ Checklist only | Add parameter fingerprint |
| Misread audit output | ⚠️ Output highlighted | Add Telegram on PHANTOM |

**Highest-value additions (30 min total):**
1. Evening token reminder Telegram (5 min — one Task Scheduler entry)
2. `git init` in moneybot folder (5 min — prevents wrong-version deploys)
3. Automate state backup as first step in auto_daily.py (10 min)
4. Telegram alert on PHANTOM positions in broker_audit.py (10 min)
