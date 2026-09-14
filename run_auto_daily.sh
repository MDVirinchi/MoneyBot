#!/data/data/com.termux/files/usr/bin/bash
# Fires from cron at 09:05 IST Mon-Fri. Runs the full MoneyBot daily pipeline.
#
# The wake lock is the point of this wrapper: auto_daily.py sleeps from ~9:05
# until the 09:14 execution window and then holds an SL-monitor loop until
# 15:30. Android killed all four processes during that sleep on 2026-08-24.
# The lock is released in a trap so it still clears if the run dies or is killed.

LOG="$HOME/auto_daily_cron.log"
# TZ is load-bearing: the proot container defaults to UTC, which is 5:30 behind
# IST. Without it datetime.now() returns UTC, so wait_until(9,14) fires at
# 2:44 PM IST and the pre-market guard rejects the 9:05 cron as "too early".
# /etc/localtime is also set in the container; this is the belt-and-braces copy.
MONEYBOT='export TZ=Asia/Kolkata PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python && cd /root/MoneyBot && python3 auto_daily.py'

cleanup() {
    termux-wake-unlock 2>/dev/null
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wake lock released" >> "$LOG"
}
trap cleanup EXIT INT TERM

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === cron trigger: acquiring wake lock ===" >> "$LOG"
termux-wake-lock

proot-distro login ubuntu -- bash -c "$MONEYBOT" >> "$LOG" 2>&1
rc=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] auto_daily.py exited rc=$rc" >> "$LOG"
exit $rc
