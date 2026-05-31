@echo off
REM Launch the Greco desktop app. Keeps a console window so any errors are visible.
REM (Once it's stable, change "python" to "pythonw" below to hide the console.)
set PYTHONUTF8=1
cd /d "%~dp0"
REM Refresh the E: PGN library first (quiet; harmless if E: is unplugged).
call "%~dp0sync_pgns.bat"
python gui.py
echo.
echo Greco has closed. Press any key to exit.
pause >nul
