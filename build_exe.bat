@echo off
REM ---------------------------------------------------------------------------
REM Build Greco.exe (PyInstaller) and deploy it to an ASCII path.
REM
REM Why deploy to C:\Users\Public\Greco instead of running from here:
REM a non-ASCII username (this profile is C:\Users\<unicode>\...) makes the
REM frozen Tcl/Tk fail to find its own files, so the app MUST run from a path
REM with no non-ASCII characters. C:\Users\Public is ASCII and always writable.
REM ---------------------------------------------------------------------------
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"

echo Building Greco.exe (this takes a few minutes)...
python -m PyInstaller --noconfirm --windowed --name Greco --icon "assets\greco.ico" --add-data "assets;assets" --add-data "openings;openings" --add-data "commentary_refs;commentary_refs" --collect-submodules markdown --collect-all anthropic --hidden-import tools.find_games gui.py
if errorlevel 1 ( echo. & echo BUILD FAILED. & pause & exit /b 1 )

echo Deploying to C:\Users\Public\Greco ...
robocopy "dist\Greco" "C:\Users\Public\Greco" /MIR /NFL /NDL /NJH /NJS /NP >nul

echo.
echo Done. Distributable exe is at:  C:\Users\Public\Greco\Greco.exe
echo This .exe is for SHARING ONLY (giving Greco to someone without Python).
echo Your desktop icon runs the LIVE SOURCE via Greco.vbs, so it always
echo reflects your latest code -- building this exe does NOT change it.
echo.
echo Re-asserting that the desktop icon points at the live source...
powershell -ExecutionPolicy Bypass -File "%~dp0verify_icon.ps1"
pause
