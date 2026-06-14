@echo off
REM Launch Greco Web (Phase 1, FastAPI) — the local browser version of Greco.
REM This is SEPARATE from the desktop app: run_greco.bat, the desktop icon,
REM and Greco.exe are all unaffected. Stop the server with Ctrl+C.
REM Uses the project venv interpreter (see run_greco.bat for why a bare "python" fails).
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist "%~dp0venv\Scripts\python.exe" (
  echo ERROR: Greco's Python environment is missing at:
  echo   "%~dp0venv\Scripts\python.exe"
  echo Rebuild it from this folder:
  echo   python -m venv venv
  echo   venv\Scripts\python -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)
echo Starting Greco Web (FastAPI)...
echo When you see "Uvicorn running on http://127.0.0.1:5000", open that address in your browser.
echo (Interactive API docs are at http://127.0.0.1:5000/docs)
echo.
"%~dp0venv\Scripts\python.exe" -m web.main
echo.
echo Greco Web has stopped. Press any key to exit.
pause >nul
