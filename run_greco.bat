@echo off
REM Launch the Greco desktop app. Keeps a console window so any errors are visible.
REM Uses the PROJECT VENV interpreter (venv\Scripts\python.exe) on purpose: Greco's
REM dependencies live in the venv, and a bare "python" resolves via PATH to the base
REM install (now Python 3.14 in Program Files), which lacks them and crashes gui.py
REM on "import httpx". For a no-console launch, use the desktop icon (-> Greco.vbs).
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist "%~dp0venv\Scripts\python.exe" (
  echo ERROR: Greco's Python environment is missing at:
  echo   "%~dp0venv\Scripts\python.exe"
  echo Rebuild it from this folder:
  echo   python -m venv venv
  echo   venv\Scripts\python -m pip install python-chess anthropic httpx matplotlib markdown truststore
  echo.
  pause
  exit /b 1
)
REM Refresh the E: PGN library first (quiet; harmless if E: is unplugged).
call "%~dp0sync_pgns.bat"
"%~dp0venv\Scripts\python.exe" gui.py
echo.
echo Greco has closed. Press any key to exit.
pause >nul
