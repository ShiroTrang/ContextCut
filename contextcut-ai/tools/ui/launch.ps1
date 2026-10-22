# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
param([string]$Project, [string]$Log, [string]$Import = "")
# Start ContextCut on a project (stderr logging to $Log); prints the pid
$env:PATH = "D:\ContextCut\env\msys64\ucrt64\bin;$env:PATH"
$env:QT_FORCE_STDERR_LOGGING = "1"
$args = @("--no-welcome")
if ($Import) { $args += @("-i", "`"$Import`"") }
$args += "`"$Project`""
$p = Start-Process -FilePath "D:\ContextCut\contextcut\stage\bin\contextcut.exe" -ArgumentList $args -RedirectStandardError $Log -RedirectStandardOutput "$Log.out" -PassThru
$p.Id
