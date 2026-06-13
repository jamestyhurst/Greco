@echo off
REM Launch Greco Web (Phase 1) — the local browser version of Greco.
REM This is SEPARATE from the desktop app: run_greco.bat, the desktop icon,
REM and Greco.exe are all unaffected. Stop the server with Ctrl+C.
set PYTHONUTF8=1
cd /d "%~dp0"
echo Starting Greco Web...
echo When you see "Running on http://127.0.0.1:5000", open that address in your browser.
echo.
python webapp.py
echo.
echo Greco Web has stopped. Press any key to exit.
pause >nul
