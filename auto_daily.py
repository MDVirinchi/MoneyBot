"""
auto_daily.py — Fully automated daily pipeline.
Runs everything in sequence: ops report, execution, monitoring.

Windows Task Scheduler should run this ONCE at 9:05 AM IST on weekdays:
  python auto_daily.py

It will:
  1. Generate today's ops report (regime, candidates, orders)
  2. Execute orders at market open (or dry-run if --dry-run flag)
  3. Monitor stop-losses every 5 minutes until market close
  4. Run broker audit after market close
  5. Log everything to auto_daily.log

Usage:
  python auto_daily.py              (LIVE — places real orders)
  python auto_daily.py --dry-run    (safe — validates but doesn't trade)
"""

import sys
import os
import time
import logging
from datetime import datetime, date
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AUTO] %(message)s",
    handlers=[
        logging.FileHandler("auto_daily.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

DRY_RUN = "--dry-run" in sys.argv


def is_weekday():
    return datetime.now().weekday() < 5



def wait_until(hour, minute):
    """Wait until a specific time today."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= target:
        return
    wait_secs = (target - now).total_seconds()
    log.info(f"Waiting until {hour:02d}:{minute:02d} ({wait_secs:.0f}s)...")
    time.sleep(wait_secs)


def run_step(description, func):
    """Run a step with error handling."""
    log.info(f"--- {description} ---")
    try:
        func()
        log.info(f"    Done.")
        return True
    except Exception as e:
        log.error(f"    FAILED: {e}", exc_info=True)
        return False


def step_ops_report():
    import daily_ops_report
    daily_ops_report.main()


def step_execute():
    import execution_engine
    if DRY_RUN:
        execution_engine.dry_run()
    else:
        execution_engine.execute_today()


def step_monitor():
    import execution_engine
    execution_engine.run_monitor()


def step_broker_audit():
    import broker_audit
    broker_audit.run_audit()


def step_status():
    import execution_engine
    execution_engine.show_status()


def step_shadow(ops: dict) -> dict:
    import shadow_engine
    return shadow_engine.run_shadow_daily(ops)


def step_comparison(shadow_summary: dict):
    import daily_comparison
    daily_comparison.run_comparison(shadow_summary)


DAILY_SUMMARY_FILE = Path("daily_summary.json")


def save_daily_summary(results):
    """One-page daily answer: did the bot behave correctly today?"""
    import json as _json

    history = []
    if DAILY_SUMMARY_FILE.exists():
        try:
            history = _json.loads(DAILY_SUMMARY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    history.append(results)
    history = history[-60:]

    DAILY_SUMMARY_FILE.write_text(
        _json.dumps(history, indent=2, default=str), encoding="utf-8")


def main():
    sep = "=" * 60
    log.info(sep)
    log.info(f"  MONEYBOT AUTO-DAILY — {date.today()}")
    log.info(f"  Mode: {'DRY RUN (no real orders)' if DRY_RUN else 'LIVE'}")
    log.info(sep)

    start_time = time.time()
    summary = {
        "date": str(date.today()),
        "mode": "DRY_RUN" if DRY_RUN else "LIVE",
        "regime": "",
        "report_generated": False,
        "shadow_ran": False,
        "execution_completed": False,
        "monitor_ran": False,
        "audit_completed": False,
        "errors": 0,
        "warnings": 0,
        "runtime_seconds": 0,
        "status": "STARTED",
    }

    if not is_weekday():
        log.info("Weekend. Nothing to do.")
        summary["status"] = "WEEKEND"
        save_daily_summary(summary)
        return

    # Time guard: refuse to run before 8:50 AM IST (pre-market — no data yet)
    now = datetime.now()
    if now.hour < 8 or (now.hour == 8 and now.minute < 50):
        log.warning(
            f"TOO EARLY: current time is {now.strftime('%H:%M')} IST. "
            f"Bot must not run before 08:50 (market opens 09:15). "
            f"Cron is set for 09:05 — check your trigger."
        )
        summary["status"] = "TOO_EARLY"
        save_daily_summary(summary)
        return

    # Step 0a: Strategy fingerprint — halt if parameters have drifted
    try:
        from strategy_fingerprint import assert_frozen, get_fingerprint, record_daily as _fp_record
        assert_frozen()
        log.info(f"Strategy fingerprint: {get_fingerprint()} — FROZEN")
    except ValueError as e:
        log.critical(str(e))
        try:
            from notify import send
            send(f"MONEYBOT HALTED\nStrategy fingerprint drift: {e}")
        except Exception:
            pass
        return
    except ImportError:
        pass

    # Step 0b: Backup state before any trading begins
    state_src = Path("execution_state.json")
    if state_src.exists():
        backup_name = f"execution_state.backup_{date.today()}.json"
        try:
            import shutil
            shutil.copy2(state_src, backup_name)
            log.info(f"State backed up → {backup_name}")
        except Exception as e:
            log.warning(f"State backup failed (non-fatal): {e}")

    # Step 1: Generate ops report
    ops = {}
    if run_step("Step 1: Generate ops report", step_ops_report):
        summary["report_generated"] = True
        try:
            import json as _j
            ops = _j.loads(Path(f"ops_log_{date.today()}.json").read_text(encoding="utf-8"))
            summary["regime"] = ops.get("regime", "UNKNOWN")
            # Record regime history and fingerprint for this day
            try:
                import json as _jj
                state = {}
                if Path("execution_state.json").exists():
                    state = _jj.loads(Path("execution_state.json").read_text(encoding="utf-8"))
                from regime_history import record as _rh_record
                _rh_record(
                    regime=ops.get("regime", "UNKNOWN"),
                    pnl_cumulative=state.get("pnl", 0.0),
                    nifty=ops.get("nifty", 0.0),
                    positions=len(state.get("positions", {})),
                )
                from strategy_fingerprint import record_daily as _fp_day
                _fp_day(regime=ops.get("regime", "UNKNOWN"),
                        pnl=state.get("pnl", 0.0))
            except Exception as _e:
                log.warning(f"Regime/fingerprint record failed (non-fatal): {_e}")
        except Exception:
            summary["regime"] = "UNKNOWN"
    else:
        summary["errors"] += 1

    # Step 1b: Shadow strategy engine (runs on same ops data, no broker calls)
    shadow_summary = {}
    if ops:
        try:
            log.info("--- Step 1b: Shadow Engine ---")
            shadow_summary = step_shadow(ops)
            summary["shadow_ran"] = True
            log.info(f"    Shadow regime={shadow_summary.get('shadow_regime')} "
                     f"positions={shadow_summary.get('positions')} "
                     f"pnl=Rs.{shadow_summary.get('total_pnl', 0):+.0f}")
        except Exception as e:
            log.error(f"    Shadow engine error (non-fatal): {e}", exc_info=True)
            summary["warnings"] += 1

    # Step 2: Wait for market open, then execute
    log.info("Waiting for 9:14 AM to execute orders...")
    wait_until(9, 14)

    if run_step("Step 2: Execute orders", step_execute):
        summary["execution_completed"] = True
    else:
        summary["errors"] += 1

    # Step 3: Monitor stop-losses during market hours
    log.info("Step 3: SL monitoring (until market close)...")
    try:
        step_monitor()
        summary["monitor_ran"] = True
    except Exception as e:
        log.error(f"Monitor error: {e}")
        summary["errors"] += 1

    # Step 4: Post-market audit
    log.info("Market closed. Running post-market checks...")
    if run_step("Step 4: Broker audit", step_broker_audit):
        summary["audit_completed"] = True
    else:
        summary["errors"] += 1
    run_step("Step 5: Final status", step_status)

    # Step 6: Daily comparison report (production vs shadow)
    if shadow_summary:
        try:
            log.info("--- Step 6: Comparison report ---")
            step_comparison(shadow_summary)
            log.info("    Done.")
        except Exception as e:
            log.error(f"    Comparison report error (non-fatal): {e}", exc_info=True)

    summary["runtime_seconds"] = round(time.time() - start_time)
    all_passed = (summary["report_generated"] and summary["execution_completed"]
                  and summary["audit_completed"] and summary["errors"] == 0)
    summary["status"] = "PASS" if all_passed else "FAIL"

    save_daily_summary(summary)

    # Step 7: Immutable audit archive
    try:
        from daily_archive import create_archive
        archive_path = create_archive()
        log.info(f"Audit archive created: {archive_path}")
    except Exception as e:
        log.warning(f"Audit archive failed (non-fatal): {e}")

    # ── TELEGRAM NOTIFICATION ────────────────────────────────────────────
    try:
        from notify import send
        msg = (f"MoneyBot {summary['date']}\n"
               f"Status: {summary['status']}\n"
               f"Regime: {summary['regime']}\n"
               f"Mode: {summary['mode']}\n"
               f"Errors: {summary['errors']}\n"
               f"Runtime: {summary['runtime_seconds']}s")
        if summary['errors'] > 0:
            msg += "\n*** CHECK auto_daily.log ***"
        send(msg)
    except Exception:
        pass

    log.info(sep)
    log.info(f"  AUTO-DAILY COMPLETE — {summary['status']}")
    log.info(sep)


if __name__ == "__main__":
    # Wrap main() so crashes ALWAYS produce a notification
    try:
        from notify import send as _notify
        _notify(f"MoneyBot STARTED — {date.today()} {'DRY_RUN' if DRY_RUN else 'LIVE'}")
    except Exception:
        pass
    try:
        main()
    except Exception as e:
        log.error(f"FATAL CRASH: {e}", exc_info=True)
        try:
            from notify import send as _notify
            _notify(f"MoneyBot CRASHED\n{date.today()}\n{type(e).__name__}: {str(e)[:200]}")
        except Exception:
            pass
