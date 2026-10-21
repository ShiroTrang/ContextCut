# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
<#
.SYNOPSIS
    Start the ContextCut built by packaging\build.ps1 (stage\bin\contextcut.exe) with the
    MSYS2 UCRT64 DLLs on PATH. Extra arguments go to ContextCut.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File packaging\run.ps1
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File packaging\run.ps1 D:\Videos\test.kdenlive
#>
param(
    # MSYS2 root; default: $env:CONTEXTCUT_MSYS2, else <repo>\..\env\msys64
    [string]$Msys2Root,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$repo = Split-Path -Parent $PSScriptRoot
if (-not $Msys2Root) { $Msys2Root = $env:CONTEXTCUT_MSYS2 }
if (-not $Msys2Root) { $Msys2Root = Join-Path (Split-Path -Parent $repo) 'env\msys64' }
$stage = if ($env:STAGE_DIR) { $env:STAGE_DIR } else { Join-Path $repo 'stage' }
$exe = Join-Path $stage 'bin\contextcut.exe'
$dlls = Join-Path $Msys2Root 'ucrt64\bin'

if (-not (Test-Path -LiteralPath $exe)) {
    [Console]::Error.WriteLine("run.ps1: '$exe' not found; build first with packaging\build.ps1.")
    exit 2
}
if (-not (Test-Path -LiteralPath $dlls)) {
    [Console]::Error.WriteLine("run.ps1: no MSYS2 UCRT64 DLLs at '$dlls'; pass -Msys2Root or set CONTEXTCUT_MSYS2.")
    exit 2
}

# Prepend so Qt/KF/MLT DLLs from this MSYS2 win over any other MinGW on the user's PATH.
$env:PATH = "$dlls;$env:PATH"
$startArgs = @{ FilePath = $exe; PassThru = $true }
if ($AppArgs) { $startArgs.ArgumentList = $AppArgs }
$proc = Start-Process @startArgs
Write-Host "ContextCut started (PID $($proc.Id))"
