' Greco launcher — refreshes the E: PGN library, then starts the GUI with UTF-8
' mode and NO console window. This is what the desktop icon runs
' (wscript.exe Greco.vbs). Pure-ASCII; paths come from %USERPROFILE%.
'
' IMPORTANT: launch the GUI with the PROJECT VENV interpreter
' (venv\Scripts\pythonw.exe), NOT a bare "pythonw". Greco's dependencies
' (httpx, python-chess, anthropic, ...) live in the venv. A bare "pythonw"
' resolves via PATH to the base Python install (now Python 3.14 in
' Program Files), which lacks those packages, so the GUI dies instantly on
' its first import -- silently, because pythonw has no console. Using the
' venv interpreter is the fix.
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
greco = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\Documents\greco"
sh.CurrentDirectory = greco
Dim q : q = Chr(34)                       ' a double-quote, for wrapping paths
Dim pyw : pyw = greco & "\venv\Scripts\pythonw.exe"

' Fail loudly (a message box), not silently, if the environment is missing.
If Not fso.FileExists(pyw) Then
  MsgBox "Greco can't start: its Python environment is missing at" & vbCrLf & _
         pyw & vbCrLf & vbCrLf & _
         "Rebuild it from the greco folder:" & vbCrLf & _
         "  python -m venv venv" & vbCrLf & _
         "  venv\Scripts\python -m pip install python-chess anthropic httpx matplotlib markdown truststore", _
         vbCritical, "Greco"
  WScript.Quit 1
End If

' Set UTF-8 mode cleanly in the process environment. (Doing this inline as
' "cmd /c set PYTHONUTF8=1 && pythonw ..." captured a trailing space -> "1 ",
' which crashes Python on startup. This avoids that.)
Dim env : Set env = sh.Environment("PROCESS")
env("PYTHONUTF8") = "1"
sh.Run q & greco & "\sync_pgns.bat" & q, 0, False
sh.Run q & pyw & q & " " & q & greco & "\gui.py" & q, 0, False
