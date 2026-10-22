# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
param([int]$AppPid)
# Ask ContextCut to close (WM_CLOSE to its main window), like clicking X; wait up to 30 s for the process to exit
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W3 {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}
"@
$main = $null
[W3]::EnumWindows({ param($h, $l) $p = 0; [void][W3]::GetWindowThreadProcessId($h, [ref]$p); if ($p -eq $AppPid -and [W3]::IsWindowVisible($h)) { $sb = New-Object System.Text.StringBuilder 512; [void][W3]::GetWindowText($h, $sb, 512); if ($sb.ToString() -like "*- ContextCut") { $script:main = $h } }; $true }, [IntPtr]::Zero) | Out-Null
if (-not $main) { "no main window"; exit 1 }
[void][W3]::PostMessage($main, 0x10, [IntPtr]::Zero, [IntPtr]::Zero)
for ($i = 0; $i -lt 60; $i++) { Start-Sleep -Milliseconds 500; if (-not (Get-Process -Id $AppPid -ErrorAction SilentlyContinue)) { "closed"; exit 0 } }
"still running"
