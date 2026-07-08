# MoneyBot — Production Change Policy

Every change to production code must pass all seven gates below.
A change that cannot satisfy every gate **waits** until it can.

This policy protects the integrity of the paper-trading validation period
and ensures that any future live capital is managed by a system whose
behavior is fully understood.

---

## The Seven Gates

### Gate 1 — Problem Statement
Write one paragraph describing the problem.
- What breaks, miscomputes, or is missing?
- How was it discovered?
- What is the user impact or risk?

If you cannot write this paragraph, you do not understand the problem yet.
Stop here.

---

### Gate 2 — Evidence
Show that the problem exists in the production codebase.
Acceptable evidence:
- A test that fails without the fix and passes with it.
- A log excerpt showing the incorrect behavior.
- A proof-of-concept reproducing the bug.

If you cannot demonstrate the problem, you may be solving the wrong thing.
Stop here.

---

### Gate 3 — Smallest Possible Fix
Make the minimum change that resolves Gate 2.
- Do not refactor surrounding code.
- Do not add features that aren't required by the fix.
- Do not change strategy parameters under any circumstances
  (those require a paper-trading restart and full re-validation).

If the fix is large, break it into smaller pieces and apply them one at a time.

---

### Gate 4 — Regression Tests
Add at least one test that:
- Fails on the original buggy code.
- Passes on the fixed code.
- Will continue to pass on any future version that preserves the fix.

Run the full suite: `python test_critical_bugs.py` must show 37/37 PASS.

---

### Gate 5 — Documentation Update
Update exactly the documents that changed:
- If execution_engine.py changed → update RELEASE_CHECKLIST.md if relevant.
- If a new failure mode exists → add it to RECOVERY_RUNBOOK.md.
- If a safeguard was added → update OPERATOR_SAFEGUARDS.md.

Do not write documentation for future intent. Document what is true now.

---

### Gate 6 — Rollback Plan
Before deploying, answer:
- What is the git commit hash before this change? (`git log -1 --format=%H`)
- Which files changed? (`git diff --name-only HEAD~1`)
- How do you revert in under 2 minutes? (`git revert HEAD` or `git checkout HEAD~1 -- filename.py`)

Write the rollback command before you deploy. Not after.

---

### Gate 7 — Paper-Trading Validation
After deploying:
- Run `python invariant_checker.py` — must pass 30/30.
- Run `python strategy_fingerprint.py` — fingerprint must be unchanged
  (unless the fix intentionally changes a strategy parameter, which requires
  a full paper-trading restart and documentation update).
- Monitor the next trading day's `auto_daily.log` for any new ERRORs.
- If production diverges from shadow strategy in an unexpected direction,
  investigate before the second trading day.

---

## Prohibited at all times

The following changes are **never permitted** during the paper-trading period,
regardless of how confident you are:

| Prohibited | Why |
|------------|-----|
| Change W_RS, W_EP | Invalidates all historical validation |
| Change TOP_N | Changes capital allocation structure |
| Change SL_PCT | Changes risk profile |
| Change RS_WINDOW or EP_WINDOW | Changes signal definition |
| Change STOCKS universe | Changes candidate pool |
| Modify backtest results | Academic integrity |
| Override an invariant check | Defeats the safety system |

If you believe any of these parameters needs to change, document the evidence
in the Research Lab (Track B). Do not touch production.

---

## Track A vs Track B

| Track A — Production | Track B — Research Lab |
|----------------------|------------------------|
| Bug fixes only | All new ideas go here |
| Full seven gates | Freely experiment |
| Strategy frozen | Strategy parameters may vary |
| Paper-trading continues | Separate backtest environment |
| This policy applies | No policy — just evidence |

Track B findings earn their way into Track A through evidence,
not enthusiasm.

---

## Version log

| Version | Date | Change | Author |
|---------|------|--------|--------|
| v1.0.0 | 2026-07-08 | Production candidate released | Rushi |
| v1.1.0 | 2026-07-08 | Operational hardening (daily_explain, backups, PHANTOM alerts) | Rushi |
| v1.2.0 | 2026-07-08 | Strategy fingerprint, regime history, weekly review, this policy | Rushi |
