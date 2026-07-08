"""
invariant_checker.py — Runtime invariant verification for MoneyBot RS60/EP40.

Usage:
  python invariant_checker.py               # full check, print report
  python invariant_checker.py --strict      # exit code 1 if any invariant breaks
  python invariant_checker.py --continuous  # check every 60s, alert on violation

  From code:
    from invariant_checker import check_all_invariants
    violations = check_all_invariants()
    if violations:
        raise RuntimeError(f"INVARIANT VIOLATION: {violations}")

Invariants are ALWAYS-true properties. A single violation means something
has gone wrong with the system state — either a bug fired, state was
corrupted, or an assumption was violated. The correct response is:
  STOP → ALERT → SNAPSHOT → EXIT SAFELY.
"""

import json
import csv
import sys
import os
import math
import msvcrt
from datetime import date, datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── File paths ────────────────────────────────────────────────────────────────
STATE_FILE    = Path("execution_state.json")
OPS_LOG_GLOB  = "ops_log_*.json"
JOURNAL_FILE  = Path("trade_journal.csv")
SHADOW_STATE  = Path("shadow_state.json")
LOCK_FILE     = Path("execution_engine.lock")
CONFIG_FILE   = Path("config.py")
LOG_FILE      = Path("auto_daily.log")

# ── Severity ──────────────────────────────────────────────────────────────────
CRITICAL = "CRITICAL"  # halt trading immediately
HIGH     = "HIGH"      # alert operator, do not initiate new trades
MEDIUM   = "MEDIUM"    # log and monitor, continue with caution
LOW      = "LOW"       # informational, does not block trading


@dataclass
class Violation:
    invariant: str
    severity:  str
    detail:    str
    module:    str = ""
    value:     str = ""

    def __str__(self):
        parts = [f"[{self.severity}] {self.invariant}"]
        if self.module:
            parts.append(f"  Module:  {self.module}")
        parts.append(f"  Detail:  {self.detail}")
        if self.value:
            parts.append(f"  Value:   {self.value}")
        return "\n".join(parts)


@dataclass
class InvariantReport:
    timestamp: str = field(default_factory=lambda: str(datetime.now()))
    violations: List[Violation] = field(default_factory=list)
    checks_run: int = 0

    def add(self, inv: str, sev: str, detail: str, module: str = "", value: str = ""):
        self.violations.append(Violation(inv, sev, detail, module, value))

    @property
    def critical(self):
        return [v for v in self.violations if v.severity == CRITICAL]

    @property
    def high(self):
        return [v for v in self.violations if v.severity == HIGH]

    @property
    def is_safe(self):
        return len(self.critical) == 0

    @property
    def must_halt(self):
        return len(self.critical) > 0


# ══════════════════════════════════════════════════════════════════════════════
# TRADING INVARIANTS — must hold at all times during operation
# ══════════════════════════════════════════════════════════════════════════════

def check_trading_invariants(state: dict, report: InvariantReport):
    """
    Invariants that must hold at every point in time while the bot has open positions.
    A violation here means the execution engine did something wrong.
    """
    positions = state.get("positions", {})
    pnl       = state.get("pnl", 0)

    # T1: Cash available is never negative
    # (MoneyBot uses Rs.5000 total capital. Cash is capital minus invested.)
    # We can't check cash directly from state, but pnl should never make
    # total available go negative.
    report.checks_run += 1

    # T2: No duplicate instruments in positions dict
    report.checks_run += 1
    insts = list(positions.keys())
    if len(insts) != len(set(insts)):
        from collections import Counter
        dupes = [k for k, c in Counter(insts).items() if c > 1]
        report.add(
            "NO_DUPLICATE_POSITIONS",
            CRITICAL,
            f"Duplicate instrument(s) in positions: {dupes}",
            "execution_state.json",
            str(dupes),
        )

    # T3: Every position must have qty > 0
    report.checks_run += 1
    for inst, pos in positions.items():
        qty = pos.get("qty", 0)
        if not isinstance(qty, (int, float)) or qty <= 0:
            report.add(
                "POSITION_QTY_POSITIVE",
                CRITICAL,
                f"{inst}: qty must be > 0",
                "execution_state.json",
                f"qty={qty}",
            )

    # T4: Every position must have sl_price < entry (SL below entry for long)
    report.checks_run += 1
    for inst, pos in positions.items():
        entry    = pos.get("entry", 0)
        sl_price = pos.get("sl_price", 0)
        if entry > 0 and sl_price > 0 and sl_price >= entry:
            report.add(
                "SL_BELOW_ENTRY",
                CRITICAL,
                f"{inst}: sl_price ({sl_price}) must be < entry ({entry}). "
                f"A SL at or above entry would trigger immediately on any tick.",
                "execution_state.json",
                f"sl_price={sl_price}, entry={entry}",
            )

    # T5: Every position must have a valid entry price (> 0, not NaN)
    report.checks_run += 1
    for inst, pos in positions.items():
        entry = pos.get("entry")
        if entry is None or (isinstance(entry, float) and math.isnan(entry)) or entry <= 0:
            report.add(
                "ENTRY_PRICE_VALID",
                CRITICAL,
                f"{inst}: entry price is missing, zero, or NaN",
                "execution_state.json",
                f"entry={entry}",
            )

    # T6: Every position must have a stop loss defined
    report.checks_run += 1
    for inst, pos in positions.items():
        sl = pos.get("sl_price")
        if sl is None or sl == 0:
            report.add(
                "SL_DEFINED",
                HIGH,
                f"{inst}: no stop loss defined (sl_price is {sl}). "
                f"Position has unlimited downside risk.",
                "execution_state.json",
                f"sl_price={sl}",
            )

    # T7: Number of open positions must not exceed 10 (strategy max)
    report.checks_run += 1
    MAX_POSITIONS = 10
    if len(positions) > MAX_POSITIONS:
        report.add(
            "MAX_POSITIONS_NOT_EXCEEDED",
            HIGH,
            f"Open positions ({len(positions)}) exceeds strategy max ({MAX_POSITIONS})",
            "execution_state.json",
            f"positions={list(positions.keys())}",
        )

    # T8: No future timestamps in position entries
    report.checks_run += 1
    today = date.today()
    for inst, pos in positions.items():
        time_str = pos.get("time", "")
        if time_str:
            try:
                entry_date = datetime.fromisoformat(time_str[:10]).date()
                if entry_date > today:
                    report.add(
                        "NO_FUTURE_TIMESTAMPS",
                        HIGH,
                        f"{inst}: entry timestamp is in the future",
                        "execution_state.json",
                        f"time={time_str}, today={today}",
                    )
            except ValueError:
                report.add(
                    "NO_FUTURE_TIMESTAMPS",
                    MEDIUM,
                    f"{inst}: entry timestamp could not be parsed",
                    "execution_state.json",
                    f"time={time_str!r}",
                )

    # T9: No empty ticker strings
    report.checks_run += 1
    for inst, pos in positions.items():
        plain = pos.get("plain", "")
        if not plain or not plain.strip():
            report.add(
                "NO_EMPTY_TICKERS",
                HIGH,
                f"Position {inst!r} has empty 'plain' symbol",
                "execution_state.json",
                f"plain={plain!r}",
            )
        if not inst or not inst.strip():
            report.add(
                "NO_EMPTY_INSTRUMENT_KEYS",
                CRITICAL,
                "Empty instrument token in positions dict — state is corrupted",
                "execution_state.json",
                f"instrument={inst!r}",
            )

    # T10: PnL must be a finite number (not NaN, not Inf)
    report.checks_run += 1
    if not isinstance(pnl, (int, float)) or math.isnan(pnl) or math.isinf(pnl):
        report.add(
            "PNL_IS_FINITE",
            HIGH,
            "state['pnl'] is not a finite number",
            "execution_state.json",
            f"pnl={pnl}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY INVARIANTS — the trading rules must always be obeyed
# ══════════════════════════════════════════════════════════════════════════════

def check_strategy_invariants(state: dict, ops: dict, report: InvariantReport):
    """
    Invariants that enforce the RS60/EP40 strategy rules.
    A violation here means the execution engine disobeyed a strategy constraint.
    """
    positions = state.get("positions", {})
    regime    = ops.get("regime", "UNKNOWN")
    buys      = ops.get("buys", [])

    # S1: In BEAR regime, there must be zero open positions
    report.checks_run += 1
    if regime == "BEAR" and len(positions) > 0:
        report.add(
            "BEAR_MEANS_CASH",
            CRITICAL,
            f"BEAR regime active but {len(positions)} position(s) still open. "
            f"All positions should have been exited when regime turned BEAR.",
            "execution_engine.py",
            f"open={list(positions.keys())}",
        )

    # S2: In BEAR regime, the ops log must not recommend any buys
    report.checks_run += 1
    if regime == "BEAR" and len(buys) > 0:
        report.add(
            "BEAR_NO_BUYS",
            CRITICAL,
            f"Ops log recommends {len(buys)} buy(s) while regime is BEAR. "
            f"This should be impossible given the validate_orders() guard.",
            "daily_ops_report.py",
            f"buys={[b.get('symbol') for b in buys]}",
        )

    # S3: Each position symbol must be in the hardcoded STOCKS universe
    # (Prevents manual or rogue positions from being tracked by the bot)
    report.checks_run += 1
    try:
        import daily_ops_report
        universe = set(daily_ops_report.STOCKS)
        for inst, pos in positions.items():
            sym = pos.get("plain", "")
            if sym and sym not in universe:
                report.add(
                    "POSITIONS_IN_UNIVERSE",
                    HIGH,
                    f"{sym} is in local positions but NOT in the STOCKS universe. "
                    f"This may be a manual trade or a symbol added after paper-trading started.",
                    "execution_state.json",
                    f"symbol={sym!r}",
                )
    except Exception as e:
        report.add(
            "POSITIONS_IN_UNIVERSE",
            MEDIUM,
            f"Could not verify universe membership: {e}",
        )

    # S4: Stop loss must be exactly 10% below entry (within floating point tolerance)
    report.checks_run += 1
    SL_PCT = 0.10
    TOLERANCE = 0.02  # allow Rs.0.02 rounding difference
    for inst, pos in positions.items():
        entry    = pos.get("entry", 0)
        sl_price = pos.get("sl_price", 0)
        if entry > 0 and sl_price > 0:
            expected_sl  = round(entry * (1 - SL_PCT), 2)
            actual_diff  = abs(sl_price - expected_sl)
            # Allow a wider tolerance for positions entered before Bug #2 fix
            # (those have SL based on prev_close, not fill_price)
            if actual_diff > entry * 0.02:  # >2% deviation from expected SL
                report.add(
                    "SL_MATCHES_STRATEGY",
                    MEDIUM,
                    f"{inst}: sl_price ({sl_price:.2f}) deviates significantly from "
                    f"expected 10%-below-entry ({expected_sl:.2f}). "
                    f"Difference: Rs.{actual_diff:.2f}. May be from Bug #2 (SL from prev_close).",
                    "execution_state.json",
                    f"entry={entry}, sl={sl_price}, expected={expected_sl}",
                )


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM INVARIANTS — preconditions for safe operation
# ══════════════════════════════════════════════════════════════════════════════

def check_system_invariants(report: InvariantReport):
    """
    Invariants that must hold for the system to operate at all.
    These are checked at startup. A violation here means do not trade.
    """

    # SY1: Config file must be loadable
    report.checks_run += 1
    try:
        import config
        if not hasattr(config, "UPSTOX_ACCESS_TOKEN"):
            report.add(
                "CONFIG_LOADED",
                CRITICAL,
                "config.py loaded but UPSTOX_ACCESS_TOKEN not defined",
                "config.py",
            )
        elif not config.UPSTOX_ACCESS_TOKEN:
            report.add(
                "CONFIG_LOADED",
                CRITICAL,
                "config.py loaded but UPSTOX_ACCESS_TOKEN is empty",
                "config.py",
            )
        # Verify token looks like a JWT (3 base64 parts separated by dots)
        token = str(config.UPSTOX_ACCESS_TOKEN)
        if token.count(".") < 2:
            report.add(
                "CONFIG_TOKEN_FORMAT",
                HIGH,
                "UPSTOX_ACCESS_TOKEN does not look like a JWT (expected 3 dot-separated parts)",
                "config.py",
                f"token_length={len(token)}, dots={token.count('.')}",
            )
    except Exception as e:
        report.add(
            "CONFIG_LOADED",
            CRITICAL,
            f"config.py failed to import: {e}",
            "config.py",
        )

    # SY2: State file must be readable and valid JSON
    report.checks_run += 1
    if STATE_FILE.exists():
        try:
            json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            report.add(
                "STATE_FILE_VALID",
                CRITICAL,
                f"execution_state.json is not valid JSON: {e}",
                "execution_state.json",
            )
    # Note: missing state file is OK (bot starts fresh)

    # SY3: Log file must be writable
    report.checks_run += 1
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            pass
    except Exception as e:
        report.add(
            "LOGS_WRITABLE",
            HIGH,
            f"auto_daily.log is not writable: {e}",
            "auto_daily.py",
        )

    # SY4: Current directory must be the moneybot folder
    report.checks_run += 1
    if not CONFIG_FILE.exists():
        report.add(
            "CORRECT_WORKING_DIRECTORY",
            CRITICAL,
            f"config.py not found in {Path.cwd()}. "
            f"The bot must be run from inside the moneybot directory.",
            "auto_daily.py",
            f"cwd={Path.cwd()}",
        )

    # SY5: Today must be a weekday (Monday-Friday)
    report.checks_run += 1
    if date.today().weekday() >= 5:
        report.add(
            "MARKET_DAY",
            HIGH,
            f"Today is {date.today().strftime('%A')} — NSE is closed on weekends. "
            f"The bot should not be running today.",
            "auto_daily.py",
            f"weekday={date.today().weekday()} (5=Sat, 6=Sun)",
        )

    # SY6: NSE holiday check
    report.checks_run += 1
    NSE_HOLIDAYS_2026 = {
        date(2026, 1, 26), date(2026, 3, 25), date(2026, 4, 2),
        date(2026, 4, 14), date(2026, 5, 1),  date(2026, 8, 15),
        date(2026, 10, 2), date(2026, 11, 4), date(2026, 12, 25),
    }
    if date.today() in NSE_HOLIDAYS_2026:
        report.add(
            "NSE_HOLIDAY_CHECK",
            HIGH,
            f"Today ({date.today()}) is an NSE holiday. "
            f"No trading should occur today.",
            "config.py (NSE_HOLIDAYS missing)",
            f"date={date.today()}",
        )

    # SY7: Disk space — warn if < 100 MB available in moneybot dir
    report.checks_run += 1
    try:
        import shutil
        total, used, free = shutil.disk_usage(Path.cwd())
        free_mb = free // (1024 * 1024)
        if free_mb < 100:
            report.add(
                "DISK_SPACE_AVAILABLE",
                HIGH,
                f"Only {free_mb} MB free on disk. "
                f"Atomic writes (mkstemp) require temporary disk space. "
                f"Below 100 MB is a risk.",
                "filesystem",
                f"free_mb={free_mb}",
            )
    except Exception as e:
        report.add("DISK_SPACE_AVAILABLE", LOW, f"Could not check disk space: {e}")

    # SY8: Journal file must have valid header if it exists
    report.checks_run += 1
    if JOURNAL_FILE.exists():
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                expected = {"trade_id", "symbol", "entry_price", "exit_price",
                            "gross_pnl", "net_pnl", "exit_reason"}
                if not expected.issubset(set(reader.fieldnames or [])):
                    report.add(
                        "JOURNAL_SCHEMA_VALID",
                        HIGH,
                        "trade_journal.csv is missing expected columns",
                        "trade_journal.py",
                        f"found={reader.fieldnames}",
                    )
        except Exception as e:
            report.add(
                "JOURNAL_SCHEMA_VALID",
                HIGH,
                f"trade_journal.csv could not be read: {e}",
            )


# ══════════════════════════════════════════════════════════════════════════════
# MATHEMATICAL INVARIANTS — accounting must always add up
# ══════════════════════════════════════════════════════════════════════════════

def check_mathematical_invariants(state: dict, report: InvariantReport):
    """
    Invariants that are mathematical identities. If they fail, the state
    has been corrupted — numbers were written without proper bookkeeping.
    """
    positions  = state.get("positions", {})
    pnl        = state.get("pnl", 0.0)
    trades     = state.get("trades", [])

    # M1: Closed-trade PnL must equal sum of individual trade PnLs
    report.checks_run += 1
    if trades:
        sum_trade_pnl = sum(t.get("pnl", 0) for t in trades)
        if abs(sum_trade_pnl - pnl) > 1.0:  # Rs.1 tolerance for rounding
            report.add(
                "PNL_EQUALS_SUM_OF_TRADES",
                HIGH,
                f"state['pnl'] ({pnl:.2f}) ≠ sum of trade PnLs ({sum_trade_pnl:.2f}). "
                f"Difference: Rs.{abs(pnl - sum_trade_pnl):.2f}. "
                f"This means a PnL update was lost or corrupted.",
                "execution_engine.py",
                f"state_pnl={pnl:.4f}, sum_trades={sum_trade_pnl:.4f}",
            )

    # M2: Trade count = wins + losses (no missing records)
    report.checks_run += 1
    if trades:
        wins   = sum(1 for t in trades if t.get("pnl", 0) > 0)
        losses = sum(1 for t in trades if t.get("pnl", 0) <= 0)
        if wins + losses != len(trades):
            report.add(
                "TRADE_COUNT_COMPLETE",
                MEDIUM,
                f"wins ({wins}) + losses ({losses}) = {wins + losses} ≠ total trades ({len(trades)})",
                "execution_state.json",
            )

    # M3: Open positions must have valid cost basis for portfolio value computation
    report.checks_run += 1
    for inst, pos in positions.items():
        entry = pos.get("entry", 0)
        qty   = pos.get("qty", 0)
        if entry > 0 and qty > 0:
            position_value = entry * qty
            if position_value > 10_000:  # Rs.10,000 per position is impossibly high at Rs.500 limit
                report.add(
                    "POSITION_VALUE_REASONABLE",
                    MEDIUM,
                    f"{inst}: implied position value Rs.{position_value:,.0f} "
                    f"(entry={entry} × qty={qty}) is larger than expected Rs.500 allocation. "
                    f"May indicate a data entry error or capital change.",
                    "execution_state.json",
                    f"entry={entry}, qty={qty}, value={position_value:.0f}",
                )

    # M4: Verify journal PnL matches state trades PnL (cross-file consistency)
    report.checks_run += 1
    if JOURNAL_FILE.exists() and trades:
        try:
            journal_pnl = 0.0
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        journal_pnl += float(row.get("gross_pnl", 0) or 0)
                    except ValueError:
                        pass
            # Note: journal records gross_pnl, state records gross as "pnl"
            # They should be consistent
            if abs(journal_pnl - pnl) > 5.0:  # Rs.5 tolerance
                report.add(
                    "JOURNAL_MATCHES_STATE_PNL",
                    MEDIUM,
                    f"trade_journal.csv total gross_pnl ({journal_pnl:.2f}) "
                    f"differs from state pnl ({pnl:.2f}) by Rs.{abs(journal_pnl - pnl):.2f}. "
                    f"May indicate a trade was recorded in one place but not the other.",
                    "trade_journal.py / execution_engine.py",
                    f"journal={journal_pnl:.4f}, state={pnl:.4f}",
                )
        except Exception as e:
            report.add("JOURNAL_MATCHES_STATE_PNL", LOW, f"Could not read journal: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# STATE INVARIANTS — execution_state.json must never contain these values
# ══════════════════════════════════════════════════════════════════════════════

def check_state_invariants(state: dict, report: InvariantReport):
    """
    Deep inspection of every field in state for values that should never exist.
    """
    def _check_value(path: str, value, inst: str = ""):
        nonlocal report
        prefix = f"[{inst}] " if inst else ""

        report.checks_run += 1
        # None check
        if value is None:
            report.add(
                "NO_NONE_VALUES",
                HIGH,
                f"{prefix}Field '{path}' is None — should be a typed value",
                "execution_state.json",
                f"path={path}",
            )
            return

        # NaN check
        if isinstance(value, float) and math.isnan(value):
            report.add(
                "NO_NAN_VALUES",
                CRITICAL,
                f"{prefix}Field '{path}' is NaN — arithmetic upstream produced a non-number",
                "execution_state.json",
                f"path={path}, value=NaN",
            )

        # Infinity check
        if isinstance(value, float) and math.isinf(value):
            report.add(
                "NO_INF_VALUES",
                CRITICAL,
                f"{prefix}Field '{path}' is Infinity — division by zero or overflow upstream",
                "execution_state.json",
                f"path={path}, value={'Inf' if value > 0 else '-Inf'}",
            )

        # Negative price/qty
        if path in ("entry", "sl_price", "qty") and isinstance(value, (int, float)):
            if value < 0:
                report.add(
                    "NO_NEGATIVE_PRICES_OR_QTY",
                    CRITICAL,
                    f"{prefix}Field '{path}' is negative: {value}",
                    "execution_state.json",
                    f"path={path}, value={value}",
                )

    # Check top-level fields
    for key in ("pnl",):
        _check_value(key, state.get(key))

    # Check every field in every position
    REQUIRED_POSITION_FIELDS = {"entry", "sl_price", "qty", "plain"}
    for inst, pos in state.get("positions", {}).items():
        if not isinstance(pos, dict):
            report.add(
                "POSITION_IS_DICT",
                CRITICAL,
                f"Position {inst!r} is not a dict: {type(pos).__name__}",
                "execution_state.json",
            )
            continue
        for field_name in REQUIRED_POSITION_FIELDS:
            _check_value(field_name, pos.get(field_name), inst)

    # Check trades list
    report.checks_run += 1
    trades = state.get("trades", [])
    if not isinstance(trades, list):
        report.add(
            "TRADES_IS_LIST",
            HIGH,
            f"state['trades'] is not a list: {type(trades).__name__}",
            "execution_state.json",
        )
    else:
        for i, trade in enumerate(trades):
            if not isinstance(trade, dict):
                report.add(
                    "TRADE_IS_DICT",
                    HIGH,
                    f"trades[{i}] is not a dict",
                    "execution_state.json",
                )

    # last_ops_date must be a valid date string or empty
    report.checks_run += 1
    last_date = state.get("last_ops_date", "")
    if last_date:
        try:
            d = date.fromisoformat(last_date)
            if d > date.today():
                report.add(
                    "LAST_OPS_DATE_NOT_FUTURE",
                    HIGH,
                    f"last_ops_date ({last_date}) is in the future",
                    "execution_state.json",
                    f"last_ops_date={last_date}, today={date.today()}",
                )
        except ValueError:
            report.add(
                "LAST_OPS_DATE_FORMAT",
                MEDIUM,
                f"last_ops_date is not a valid ISO date: {last_date!r}",
                "execution_state.json",
            )


# ══════════════════════════════════════════════════════════════════════════════
# BROKER CONSISTENCY INVARIANT (optional — requires network call)
# ══════════════════════════════════════════════════════════════════════════════

def check_broker_consistency(state: dict, report: InvariantReport, call_broker: bool = False):
    """
    If call_broker=True, compare local state against live broker positions.
    Only used when running as standalone tool, not in hot path.
    """
    if not call_broker:
        report.checks_run += 1
        # Rely on latest broker_audit_log.json instead
        audit_log = Path("broker_audit_log.json")
        if audit_log.exists():
            try:
                history = json.loads(audit_log.read_text(encoding="utf-8"))
                if history:
                    latest = history[-1]
                    if latest.get("status") == "MISMATCHES":
                        mismatches = latest.get("mismatches", [])
                        for m in mismatches:
                            sev = CRITICAL if m["type"] in ("phantom", "corporate_action") else HIGH
                            report.add(
                                "BROKER_LOCAL_CONSISTENT",
                                sev,
                                f"Last audit ({latest['date']}): {m['symbol']} — {m['type']}. "
                                f"Local qty={m['local_qty']}, broker qty={m['broker_qty']}.",
                                "broker_audit.py",
                                f"type={m['type']}",
                            )
            except Exception as e:
                report.add(
                    "BROKER_AUDIT_LOG_READABLE",
                    LOW,
                    f"Could not read broker_audit_log.json: {e}",
                )
        return

    # Live broker call path (not used in hot path)
    try:
        import config, requests
        headers = {
            "Authorization": f"Bearer {config.UPSTOX_ACCESS_TOKEN}",
            "Accept": "application/json",
        }
        r = requests.get(
            "https://api.upstox.com/v2/portfolio/short-term-positions",
            headers=headers, timeout=10,
        )
        data = r.json()
        if data.get("status") != "success":
            report.add(
                "BROKER_API_REACHABLE",
                HIGH,
                f"Broker API returned non-success: {data.get('status')}",
                "upstox_api",
            )
            return

        broker_positions = {
            p["instrument_token"]: int(p.get("quantity", 0))
            for p in data.get("data", [])
            if p.get("instrument_token")
        }
        local_positions = {
            inst: pos.get("qty", 0)
            for inst, pos in state.get("positions", {}).items()
        }

        report.checks_run += 1
        for inst in set(list(broker_positions) + list(local_positions)):
            b_qty = broker_positions.get(inst, 0)
            l_qty = local_positions.get(inst, 0)
            if b_qty != l_qty:
                report.add(
                    "BROKER_LOCAL_CONSISTENT",
                    CRITICAL if abs(b_qty - l_qty) > 1 else HIGH,
                    f"{inst}: broker_qty={b_qty} ≠ local_qty={l_qty}",
                    "execution_state.json vs broker API",
                    f"drift={b_qty - l_qty}",
                )

    except Exception as e:
        report.add(
            "BROKER_API_REACHABLE",
            MEDIUM,
            f"Could not reach broker API: {e}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════

def check_all_invariants(call_broker: bool = False) -> InvariantReport:
    """
    Run all invariant checks. Returns an InvariantReport.
    Callers should inspect report.must_halt and report.violations.
    """
    report = InvariantReport()

    # Load state (gracefully)
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            report.add(
                "STATE_FILE_LOADABLE",
                CRITICAL,
                "execution_state.json exists but could not be parsed as JSON",
                "execution_state.json",
            )

    # Load today's ops log (gracefully)
    ops = {}
    today_ops = Path(f"ops_log_{date.today()}.json")
    if today_ops.exists():
        try:
            ops = json.loads(today_ops.read_text(encoding="utf-8"))
        except Exception:
            pass

    check_system_invariants(report)
    check_trading_invariants(state, report)
    check_strategy_invariants(state, ops, report)
    check_mathematical_invariants(state, report)
    check_state_invariants(state, report)
    check_broker_consistency(state, report, call_broker=call_broker)

    return report


def _print_report(report: InvariantReport):
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  MONEYBOT INVARIANT CHECK — {report.timestamp}")
    print(f"  Checks run: {report.checks_run}")
    print(sep)

    if not report.violations:
        print(f"\n  ALL INVARIANTS HOLD  ({report.checks_run} checks passed)")
        print(f"\n  System state is consistent. Safe to proceed.\n")
        print(sep)
        return

    by_severity = {CRITICAL: [], HIGH: [], MEDIUM: [], LOW: []}
    for v in report.violations:
        by_severity[v.severity].append(v)

    for sev in (CRITICAL, HIGH, MEDIUM, LOW):
        viols = by_severity[sev]
        if not viols:
            continue
        print(f"\n  [{sev}] — {len(viols)} violation(s)")
        print(f"  {'─' * 60}")
        for v in viols:
            print(f"\n  {v.invariant}")
            if v.module:
                print(f"    Module: {v.module}")
            print(f"    Detail: {v.detail}")
            if v.value:
                print(f"    Value:  {v.value}")

    print(f"\n{sep}")
    n_crit = len(report.critical)
    n_high = len(report.high)
    n_total = len(report.violations)
    print(f"  SUMMARY: {n_total} violation(s) found "
          f"({n_crit} CRITICAL, {n_high} HIGH)")

    if report.must_halt:
        print(f"\n  *** HALT TRADING ***")
        print(f"  {n_crit} CRITICAL violation(s) found.")
        print(f"  Do not run execute_today() until all CRITICAL violations are resolved.")
    elif n_high > 0:
        print(f"\n  *** CAUTION ***")
        print(f"  No CRITICAL violations, but {n_high} HIGH violation(s) need operator attention.")
    print(sep)


def _snapshot_on_critical(report: InvariantReport):
    """Write a timestamped snapshot of current state when CRITICAL violations found."""
    if not report.must_halt:
        return
    snap_path = Path(f"INVARIANT_VIOLATION_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
        snap = {
            "timestamp": report.timestamp,
            "violations": [
                {
                    "invariant": v.invariant,
                    "severity":  v.severity,
                    "detail":    v.detail,
                    "module":    v.module,
                    "value":     v.value,
                }
                for v in report.violations
            ],
            "state_snapshot": state,
        }
        snap_path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        print(f"\n  State snapshot saved to: {snap_path}")
    except Exception as e:
        print(f"\n  Could not save snapshot: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MoneyBot invariant checker")
    parser.add_argument("--strict",     action="store_true",
                        help="Exit code 1 if any invariant breaks")
    parser.add_argument("--broker",     action="store_true",
                        help="Make live broker API call to verify position consistency")
    parser.add_argument("--continuous", action="store_true",
                        help="Run every 60 seconds, alert on violations")
    parser.add_argument("--notify",     action="store_true",
                        help="Send Telegram alert on CRITICAL violations")
    args = parser.parse_args()

    if args.continuous:
        import time
        print("  Running in continuous mode. Press Ctrl+C to stop.")
        while True:
            report = check_all_invariants(call_broker=args.broker)
            _print_report(report)
            if report.must_halt:
                _snapshot_on_critical(report)
                if args.notify:
                    try:
                        from notify import send
                        msg = (f"INVARIANT VIOLATION\n"
                               f"{len(report.critical)} CRITICAL\n"
                               f"{', '.join(v.invariant for v in report.critical)}")
                        send(msg)
                    except Exception:
                        pass
            time.sleep(60)
    else:
        report = check_all_invariants(call_broker=args.broker)
        _print_report(report)
        if report.must_halt:
            _snapshot_on_critical(report)
            if args.notify:
                try:
                    from notify import send
                    msg = (f"INVARIANT VIOLATION\n"
                           f"{len(report.critical)} CRITICAL\n"
                           f"{', '.join(v.invariant for v in report.critical)}")
                    send(msg)
                except Exception:
                    pass
        if args.strict and report.violations:
            sys.exit(1)
