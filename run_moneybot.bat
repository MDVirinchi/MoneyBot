@echo off
REM MoneyBot Auto-Daily Runner
REM Schedule this in Windows Task Scheduler to run at 9:05 AM on weekdays
REM
REM For DRY RUN (safe, no real orders):
REM   Change the last line to: python auto_daily.py --dry-run
REM
REM For LIVE TRADING (real orders):
REM   Change the last line to: python auto_daily.py

cd /d C:\Users\rushi\Downloads\moneybot
python auto_daily.py --dry-run
