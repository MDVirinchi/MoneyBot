@echo off
echo ============================================================
echo  MoneyBot RS60/EP40 -- Daily Operations
echo  Strategy FROZEN: RS=60%% EP=40%% Top-10 Rebal-10d SL-10%%
echo ============================================================
echo.
echo [1/2] Running ops report...
python "%~dp0daily_ops_report.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: daily_ops_report.py failed. Check the output above.
    echo Do NOT enter any values in the workbook until the error is resolved.
    pause
    exit /b 1
)
echo.
echo [2/2] Opening dashboard...
python "%~dp0dashboard.py"
echo.
echo ============================================================
echo  DONE. Now:
echo  1. Enter Nifty close, 50-DMA, 200-DMA in Daily_Ops_Log
echo  2. Verify Regime in col G matches what the report printed
echo  3. Update Current Close for all open positions
echo  4. Check Status column -- act on any SL TRIGGERED
echo  5. Save workbook (Ctrl+S)
echo ============================================================
pause
