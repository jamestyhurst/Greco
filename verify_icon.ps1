# verify_icon.ps1 — DOCTRINE: keep the Greco desktop icon wired to the LIVE source.
#
# The icon should always launch:  wscript.exe "<...>\greco\Greco.vbs" -> pythonw gui.py
# so every code change is reflected with no rebuild. This script checks that and
# repairs the shortcut if it has drifted (e.g. someone repointed it at a frozen
# .exe). It is idempotent and safe to run after every change to Greco.
#
# Usage:   powershell -ExecutionPolicy Bypass -File verify_icon.ps1
#
# NOTE: WScript.Shell COM cannot create this shortcut correctly under a non-ASCII
# username (it mangles the path to '???'), so we use the IShellLinkW shell API.

$ErrorActionPreference = 'Stop'

$grecoDir = Join-Path $env:USERPROFILE 'Documents\greco'
$vbs      = Join-Path $grecoDir 'Greco.vbs'
$ico      = Join-Path $grecoDir 'assets\greco.ico'
$wscript  = Join-Path $env:WINDIR 'System32\wscript.exe'
$desktop  = [Environment]::GetFolderPath('DesktopDirectory')   # handles OneDrive redirection
$lnk      = Join-Path $desktop 'Greco.lnk'

if (-not (Test-Path $vbs)) { Write-Error "Greco.vbs not found at $vbs - is the source in place?"; exit 1 }

function Test-IconOK([string]$path) {
  if (-not (Test-Path $path)) { return $false }
  $b    = [System.IO.File]::ReadAllBytes($path)
  $ansi = [System.Text.Encoding]::Default.GetString($b)
  $need = [System.Text.Encoding]::Unicode.GetBytes('Greco.vbs')   # args stored UTF-16
  $hasVbs = $false
  for ($i = 0; $i -le $b.Length - $need.Length; $i++) {
    $ok = $true
    for ($j = 0; $j -lt $need.Length; $j++) { if ($b[$i+$j] -ne $need[$j]) { $ok = $false; break } }
    if ($ok) { $hasVbs = $true; break }
  }
  return ($hasVbs -and ($ansi -match 'wscript'))
}

function New-GrecoIcon {
  if (-not ([System.Management.Automation.PSTypeName]'GrecoLnk.Maker').Type) {
    Add-Type -Language CSharp -TypeDefinition @'
using System; using System.Runtime.InteropServices; using System.Runtime.InteropServices.ComTypes; using System.Text;
namespace GrecoLnk {
  [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr fd, uint fl);
    void GetIDList(out IntPtr ppidl); void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder n, int c);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string n);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder d, int c);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string d);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder a, int c);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string a);
    void GetHotkey(out short k); void SetHotkey(short k);
    void GetShowCmd(out int c); void SetShowCmd(int c);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder p, int c, out int i);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string p, int i);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string p, uint r);
    void Resolve(IntPtr hwnd, uint fl); void SetPath([MarshalAs(UnmanagedType.LPWStr)] string f);
  }
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class ShellLink { }
  public static class Maker {
    public static void Create(string lnk, string target, string args, string workdir, string icon, int idx, string desc) {
      IShellLinkW l = (IShellLinkW)new ShellLink();
      l.SetPath(target); if (args!=null) l.SetArguments(args);
      if (workdir!=null) l.SetWorkingDirectory(workdir);
      if (icon!=null) l.SetIconLocation(icon, idx);
      if (desc!=null) l.SetDescription(desc); l.SetShowCmd(1);
      IPersistFile pf = (IPersistFile)l; pf.Save(lnk, false);
      Marshal.ReleaseComObject(pf); Marshal.ReleaseComObject(l);
    }
  }
}
'@
  }
  # Save to an ASCII temp path first (COM Save mangles non-ASCII dest paths),
  # then copy to the (possibly Unicode) desktop with .NET.
  $temp = Join-Path $env:PUBLIC 'Greco_iconfix_temp.lnk'
  [GrecoLnk.Maker]::Create($temp, $wscript, ('"' + $vbs + '"'), $grecoDir, $ico, 0, 'Greco - Chess Game Analyzer (live source)')
  [System.IO.File]::Copy($temp, $lnk, $true)
  [System.IO.File]::Delete($temp)
}

if (Test-IconOK $lnk) {
  Write-Output "OK: the Greco desktop icon already launches the live source."
  Write-Output "    -> $wscript `"$vbs`""
} else {
  Write-Output "Icon is missing or drifted - repairing..."
  New-GrecoIcon
  if (Test-IconOK $lnk) {
    Write-Output "REPAIRED: the Greco desktop icon now launches the live source."
    Write-Output "    -> $wscript `"$vbs`""
  } else {
    Write-Error "Could not repair the Greco desktop icon at $lnk"; exit 1
  }
}
