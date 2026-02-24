@echo off
:: 台股每日盤後自動掃描
:: 執行時間：平日 14:35（收盤後約 1 小時，確保 yfinance 數據更新）

set PROJECT=S:\股票筆記
set PYTHON=C:\ProgramData\Anaconda3\python.exe
set LOGDIR=%PROJECT%\journals\logs

:: 用 PowerShell 取得格式正確的日期
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i

set LOGFILE=%LOGDIR%\%TODAY%_scan.log

:: 建立 log 目錄（若不存在）
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ============================================================ >> "%LOGFILE%"
echo 執行時間: %TODAY% >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"

echo [1/3] 執行持倉健診... >> "%LOGFILE%"
"%PYTHON%" "%PROJECT%\scripts\portfolio_report.py" >> "%LOGFILE%" 2>&1

echo. >> "%LOGFILE%"
echo [2/3] 記錄淨值快照... >> "%LOGFILE%"
"%PYTHON%" "%PROJECT%\scripts\portfolio_log.py" >> "%LOGFILE%" 2>&1

echo. >> "%LOGFILE%"
echo [3/3] 執行 Watchlist 掃描... >> "%LOGFILE%"
"%PYTHON%" "%PROJECT%\scripts\watchlist_scan.py" >> "%LOGFILE%" 2>&1

echo. >> "%LOGFILE%"
echo 完成。 >> "%LOGFILE%"
