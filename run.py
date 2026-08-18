"""
MoneyBot — starts all income streams simultaneously.
Usage:  python run.py
"""

import argparse
import threading
import time
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# BUG FIX 3: Configure root logger so run.py's own log statements are not silent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MONEYBOT] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("moneybot_main.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

RESTART_DELAY = 60  # seconds to wait before restarting a crashed module


def parse_args():
    parser = argparse.ArgumentParser(description="Start the MoneyBot orchestrator")
    parser.add_argument("--stop-after-minutes", type=int, help="Stop the bot after N minutes")
    parser.add_argument("--stop-at", help="Stop the bot at HH:MM local time")
    return parser.parse_args()


def parse_stop_time(stop_at: str):
    try:
        hour, minute = map(int, stop_at.split(":"))
    except ValueError as exc:
        raise ValueError("--stop-at must be in HH:MM format") from exc

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def should_stop(stop_target):
    if stop_target is None:
        return False
    if isinstance(stop_target, float):
        return time.monotonic() >= stop_target
    return datetime.now() >= stop_target


# BUG FIX 1: Supervisor loops — if a module crashes, restart it after a delay.
# Without this, a single API timeout kills the trading thread permanently.
# The bot keeps "running" but no scans, no stop-loss monitoring, no trades.

def start_trading():
    import trading_bot
    while True:
        try:
            log.info("Trading module starting...")
            trading_bot.run()
        except Exception as e:
            log.error(f"Trading bot crashed: {e}", exc_info=True)
            log.info(f"Trading module will restart in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)

def start_freelance():
    import freelance_bot
    while True:
        try:
            log.info("Freelance module starting...")
            freelance_bot.run()
        except Exception as e:
            log.error(f"Freelance bot crashed: {e}", exc_info=True)
            log.info(f"Freelance module will restart in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)

def start_fiverr():
    import fiverr_bot
    while True:
        try:
            log.info("Fiverr module starting...")
            fiverr_bot.run()
        except Exception as e:
            log.error(f"Fiverr bot crashed: {e}", exc_info=True)
            log.info(f"Fiverr module will restart in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)

# BUG FIX 2: Dashboard refresh writes HTML but only opens the browser ONCE.
# Previously webbrowser.open() was called every 5 minutes → 96 tabs/day.

_dashboard_opened = False

def show_dashboard_loop():
    global _dashboard_opened
    import dashboard
    while True:
        try:
            if _dashboard_opened:
                dashboard.refresh_only()
            else:
                dashboard.main()
                _dashboard_opened = True
        except Exception as e:
            log.error(f"Dashboard error: {e}", exc_info=True)
        time.sleep(300)


if __name__ == "__main__":
    import config

    args = parse_args()
    stop_target = None

    if args.stop_after_minutes is not None:
        if args.stop_after_minutes <= 0:
            raise SystemExit("--stop-after-minutes must be greater than 0")
        stop_target = time.monotonic() + (args.stop_after_minutes * 60)
        log.info(f"Scheduled stop: {args.stop_after_minutes} minutes from now")
    elif args.stop_at:
        stop_target = parse_stop_time(args.stop_at)
        log.info(f"Scheduled stop: {args.stop_at}")

    log.info("MoneyBot starting...")

    missing = []
    if not config.UPSTOX_API_KEY:   missing.append("UPSTOX_API_KEY (trading)")
    if not config.ANTHROPIC_API_KEY: missing.append("ANTHROPIC_API_KEY (AI freelance)")

    if missing:
        log.warning("Missing API keys in config.py:")
        for m in missing: log.warning(f"   - {m}")
        log.warning("Edit config.py and re-run.")
    else:
        threads = [
            threading.Thread(target=start_trading,   daemon=True, name="Trading"),
            threading.Thread(target=start_freelance, daemon=True, name="Freelance"),
            threading.Thread(target=show_dashboard_loop, daemon=True, name="Dashboard"),
        ]
        for t in threads:
            log.info(f"Starting {t.name} module")
            t.start()

        log.info("MoneyBot is running. Press Ctrl+C to stop.")
        try:
            while not should_stop(stop_target):
                time.sleep(60)
            log.info("Scheduled stop time reached. Stopping MoneyBot.")
        except KeyboardInterrupt:
            log.info("MoneyBot stopped.")
