' Greco launcher — used by the desktop shortcut.
' (1) Refreshes the E: PGN library, then (2) starts the GUI with UTF-8 mode and
' NO console window. Pure-ASCII on purpose (paths come from %USERPROFILE% / PATH),
' so the Chinese-username path is never mis-encoded.
Set sh = CreateObject("WScript.Shell")
greco = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\Documents\greco"
sh.CurrentDirectory = greco
' Sync chess PGNs C: -> E: in the background (hidden, don't wait; safe if E: is absent).
sh.Run """" & greco & "\sync_pgns.bat""", 0, False
' Launch the GUI.
sh.Run "cmd /c set PYTHONUTF8=1 && pythonw gui.py", 0, False
