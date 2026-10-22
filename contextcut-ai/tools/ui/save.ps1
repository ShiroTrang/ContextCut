# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
param([int]$AppPid)
# Save the open project in ContextCut: Ctrl+S on the main window, Enter on the "Information" box (first save of an upgraded project)
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@
Add-Type -AssemblyName System.Windows.Forms
function Get-Windows {
  $list = New-Object System.Collections.ArrayList
  [W]::EnumWindows({ param($h, $l) $p = 0; [void][W]::GetWindowThreadProcessId($h, [ref]$p); if ($p -eq $AppPid -and [W]::IsWindowVisible($h)) { $sb = New-Object System.Text.StringBuilder 512; [void][W]::GetWindowText($h, $sb, 512); [void]$list.Add(@($h, $sb.ToString())) }; $true }, [IntPtr]::Zero) | Out-Null
  return $list
}
$main = Get-Windows | Where-Object { $_[1] -like "*ContextCut*" -and $_[1] -notlike "Information*" } | Select-Object -First 1
if (-not $main) { "no main window"; exit 1 }
[void][W]::SetForegroundWindow($main[0]); Start-Sleep -Milliseconds 400
[System.Windows.Forms.SendKeys]::SendWait("^s")
for ($i = 0; $i -lt 10; $i++) {
  Start-Sleep -Milliseconds 500
  $info = Get-Windows | Where-Object { $_[1] -like "Information*" -or $_[1] -like "Warning*" } | Select-Object -First 1
  if ($info) { [void][W]::SetForegroundWindow($info[0]); Start-Sleep -Milliseconds 300; [System.Windows.Forms.SendKeys]::SendWait("{ENTER}"); "answered: $($info[1])"; break }
}
Get-Windows | ForEach-Object { "window: $($_[1])" }
