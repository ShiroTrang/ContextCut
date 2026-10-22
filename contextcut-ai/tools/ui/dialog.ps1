# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
param([int]$AppPid, [string]$TitleLike = "ContextCut*AI mu*", [string]$Action = "show", [int]$X = 0, [int]$Y = 0, [string]$Out = "", [int]$HoldSeconds = 0, [int]$TimeoutSeconds = 0)
# show: raise the dialog (topmost, no activation) and screenshot it to $Out; prints window and client rects.
# click: post a left click at client coordinates ($X, $Y) of the dialog (works even when it is behind other windows).
# accept / reject: click "Xuat" / "Khong xuat" of ContextCut's export confirmation. -TimeoutSeconds waits for the
# dialog, -HoldSeconds keeps it unanswered first. Kdenlive's "Save changes?" box: -TitleLike "Warning*" -Action click
# -X 360 (Save) / 452 (Do Not Save) / 537 (Cancel) -Y 63.
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W5 {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
}
"@
[void][W5]::SetProcessDPIAware()
function Find-Box {
$script:box = $null
[W5]::EnumWindows({ param($h, $l) $p = 0; [void][W5]::GetWindowThreadProcessId($h, [ref]$p); if ($p -eq $AppPid -and [W5]::IsWindowVisible($h)) { $sb = New-Object System.Text.StringBuilder 512; [void][W5]::GetWindowText($h, $sb, 512); if ($sb.ToString() -like $TitleLike) { $script:box = $h } }; $true }, [IntPtr]::Zero) | Out-Null
return $script:box
}
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while (-not ($box = Find-Box)) { if ((Get-Date) -gt $deadline) { "no dialog"; exit 1 }; Start-Sleep -Milliseconds 300 }
"$(Get-Date -Format HH:mm:ss.fff) dialog found"
if ($HoldSeconds) { Start-Sleep -Seconds $HoldSeconds }
$r = New-Object W5+RECT; [void][W5]::GetWindowRect($box, [ref]$r)
$c = New-Object W5+RECT; [void][W5]::GetClientRect($box, [ref]$c)
$o = New-Object W5+POINT; [void][W5]::ClientToScreen($box, [ref]$o)
"window $($r.L),$($r.T) $($r.R - $r.L)x$($r.B - $r.T); client origin $($o.X),$($o.Y) size $($c.R)x$($c.B)"
if ($Action -eq "show") {
  # HWND_TOPMOST, SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE
  [void][W5]::SetWindowPos($box, [IntPtr](-1), 0, 0, 0, 0, 0x13)
  Start-Sleep -Milliseconds 400
  Add-Type -AssemblyName System.Drawing
  $bmp = New-Object System.Drawing.Bitmap $c.R, $c.B
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($o.X, $o.Y, 0, 0, (New-Object System.Drawing.Size $c.R, $c.B))
  $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
  "saved $Out"
} else {
  # accept = "Xuat" (left button), reject = "Khong xuat" (right, default): offsets measured on the box (22/10)
  if ($Action -eq "accept") { $X = $c.R - 147; $Y = $c.B - 25 } elseif ($Action -eq "reject") { $X = $c.R - 53; $Y = $c.B - 25 }
  $lp = [IntPtr](($Y -shl 16) -bor ($X -band 0xFFFF))
  [void][W5]::PostMessage($box, 0x0200, [IntPtr]0, $lp)   # WM_MOUSEMOVE
  [void][W5]::PostMessage($box, 0x0201, [IntPtr]1, $lp)   # WM_LBUTTONDOWN
  Start-Sleep -Milliseconds 80
  [void][W5]::PostMessage($box, 0x0202, [IntPtr]0, $lp)   # WM_LBUTTONUP
  "$(Get-Date -Format HH:mm:ss.fff) clicked $X,$Y"
}
