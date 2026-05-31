' Greco launcher — refreshes the E: PGN library, then starts the GUI with UTF-8
' mode and NO console window. Optional (the desktop shortcut currently uses
' run_greco.bat). Pure-ASCII; paths come from %USERPROFILE% / PATH.
Set sh = CreateObject("WScript.Shell")
greco = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\Documents\greco"
sh.CurrentDirectory = greco
' Set UTF-8 mode cleanly in the process environment. (Doing this inline as
' "cmd /c set PYTHONUTF8=1 && pythonw ..." captured a trailing space -> "1 ",
' which crashes Python on startup. This avoids that.)
Dim env : Set env = sh.Environment("PROCESS")
env("PYTHONUTF8") = "1"
sh.Run """" & greco & "\sync_pgns.bat""", 0, False
sh.Run "pythonw """ & greco & "\gui.py""", 0, False
