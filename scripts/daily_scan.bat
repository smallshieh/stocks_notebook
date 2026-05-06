@echo off
chcp 65001 >nul
set PROJECT=S:\股票筆記
set PYTHON=S:\股票筆記\.venv\Scripts\python.exe
set LOGDIR=%PROJECT%\journals\logs

if not "%~1"=="" (
    set REVIEW_DATE=%~1
) else (
    for /f %%i in ('"%PYTHON%" -c "from curl_cffi import requests as creq; import yfinance as yf; s=creq.Session(verify=False, impersonate='chrome'); d=yf.Ticker('2330.TW', session=s).history(period='5d'); print(d.index[-1].strftime('%%Y-%%m-%%d') if d is not None and not d.empty else __import__('datetime').date.today().isoformat())" 2^>nul') do set REVIEW_DATE=%%i
)
set TODAY=%REVIEW_DATE%

set LOGFILE=%LOGDIR%\%TODAY%_scan.log

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ============================================================ >> "%LOGFILE%"
echo Start: %TODAY% >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"

echo [1/5] portfolio_report.py >> "%LOGFILE%"
"%PYTHON%" "%PROJECT%\scripts\portfolio_report.py" --date=%TODAY% >> "%LOGFILE%" 2>&1
echo [exit: %ERRORLEVEL%] >> "%LOGFILE%"

echo. >> "%LOGFILE%"
echo [2/5] portfolio_log.py >> "%LOGFILE%"
"%PYTHON%" "%PROJECT%\scripts\portfolio_log.py" --date %TODAY% >> "%LOGFILE%" 2>&1
echo [exit: %ERRORLEVEL%] >> "%LOGFILE%"

echo. >> "%LOGFILE%"
echo [3/5] watchlist_scan.py >> "%LOGFILE%"
"%PYTHON%" "%PROJECT%\scripts\watchlist_scan.py" --date %TODAY% >> "%LOGFILE%" 2>&1
echo [exit: %ERRORLEVEL%] >> "%LOGFILE%"

echo. >> "%LOGFILE%"
echo [4/5] wave_score_scan.py >> "%LOGFILE%"
"%PYTHON%" "%PROJECT%\scripts\wave_score_scan.py" --date %TODAY% >> "%LOGFILE%" 2>&1
echo [exit: %ERRORLEVEL%] >> "%LOGFILE%"

echo. >> "%LOGFILE%"
echo [5/5] event_detector.py >> "%LOGFILE%"
"%PYTHON%" "%PROJECT%\scripts\event_detector.py" --date %TODAY% >> "%LOGFILE%" 2>&1
echo [exit: %ERRORLEVEL%] >> "%LOGFILE%"

echo. >> "%LOGFILE%"
echo Done. >> "%LOGFILE%"
exit /b 0
