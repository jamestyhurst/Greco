@echo off
REM Greco: copy chess PGNs from the C: library to the E: library.
REM Additive + safe: copies new/updated .pgn files, preserves the folder
REM structure, and NEVER deletes anything on E:. Always exits 0 so the
REM scheduled task reports success even if E: is unplugged.
REM (%USERPROFILE% is expanded at runtime, so this file stays pure-ASCII and
REM  is immune to the cmd codepage issue with the Chinese username path.)
robocopy "%USERPROFILE%\Documents\Chess Game Files" "E:\Chess\PGNs" *.pgn /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul 2>&1
exit /b 0
