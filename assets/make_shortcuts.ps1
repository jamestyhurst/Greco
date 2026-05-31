# Greco — (re)create the Windows shortcuts. Run with:
#   powershell -ExecutionPolicy Bypass -File assets\make_shortcuts.ps1
#
# Uses the Unicode-native IShellLinkW / IPersistFile COM interfaces. This is
# REQUIRED on this machine: the usual WScript.Shell.CreateShortcut routes the
# path through the system ANSI codepage, which cannot represent the Chinese
# username (詹天哲) and fails to save. IPersistFile.Save takes a wide string.
$cs = @"
using System;
using System.Runtime.InteropServices;
namespace GrecoShortcut {
  [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IShellLinkW {
    void GetPath(IntPtr a, int b, IntPtr c, uint d); void GetIDList(out IntPtr a); void SetIDList(IntPtr a);
    void GetDescription(IntPtr a, int b); void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetWorkingDirectory(IntPtr a, int b); void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetArguments(IntPtr a, int b); void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetHotkey(out short a); void SetHotkey(short a); void GetShowCmd(out int a); void SetShowCmd(int a);
    void GetIconLocation(IntPtr a, int b, out int c); void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s, int i);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s, uint r); void Resolve(IntPtr h, uint f);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
  }
  [ComImport, Guid("0000010B-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IPersistFile {
    void GetClassID(out Guid a); [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint m);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string f, [MarshalAs(UnmanagedType.Bool)] bool r);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f); void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string f);
  }
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")] public class ShellLink { }
  public static class Lnk {
    public static void Create(string lnk, string target, string args, string wd, string icon, int iconIdx, string desc, int show) {
      var sl = (IShellLinkW)(new ShellLink());
      sl.SetPath(target);
      if (!string.IsNullOrEmpty(args)) sl.SetArguments(args);
      if (!string.IsNullOrEmpty(wd)) sl.SetWorkingDirectory(wd);
      if (!string.IsNullOrEmpty(icon)) sl.SetIconLocation(icon, iconIdx);
      if (!string.IsNullOrEmpty(desc)) sl.SetDescription(desc);
      sl.SetShowCmd(show);
      ((IPersistFile)sl).Save(lnk, true);
    }
  }
}
"@
Add-Type -TypeDefinition $cs -Language CSharp

$greco = Split-Path -Parent $PSScriptRoot          # ...\greco\assets -> ...\greco
$desktop = [Environment]::GetFolderPath('Desktop')
$startup = [Environment]::GetFolderPath('Startup')

# Desktop shortcut: launch the GUI via run_greco.bat (reliable; shows a console).
# (Greco.vbs is the future no-console launcher, for when we package the app.)
[GrecoShortcut.Lnk]::Create((Join-Path $desktop 'Greco.lnk'),
  "$greco\run_greco.bat", "",
  $greco, "$greco\assets\greco.ico", 0, "Greco - Chess Game Analyzer", 1)

# Startup shortcut: sync chess PGNs C: -> E: at every logon (minimized).
[GrecoShortcut.Lnk]::Create((Join-Path $startup 'Greco PGN Sync.lnk'),
  "$greco\sync_pgns.bat", "", $greco, "$greco\assets\greco.ico", 0,
  "Greco: sync chess PGNs C: to E: at logon", 7)

Write-Output "Desktop  : $(Test-Path (Join-Path $desktop 'Greco.lnk'))"
Write-Output "Startup  : $(Test-Path (Join-Path $startup 'Greco PGN Sync.lnk'))"
