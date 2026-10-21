# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
<#
.SYNOPSIS
    One-command ContextCut build: runs packaging/build.sh in the project's own MSYS2 UCRT64.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipDeps
#>
[CmdletBinding()]
param(
    # MSYS2 root; default: $env:CONTEXTCUT_MSYS2, else <repo>\..\env\msys64
    [string]$Msys2Root,
    [switch]$SkipDeps,
    [switch]$Reconfigure,
    [switch]$ConfigureOnly
)

$repo = Split-Path -Parent $PSScriptRoot
if (-not $Msys2Root) { $Msys2Root = $env:CONTEXTCUT_MSYS2 }
if (-not $Msys2Root) { $Msys2Root = Join-Path (Split-Path -Parent $repo) 'env\msys64' }
$Msys2Root = [IO.Path]::GetFullPath($Msys2Root).TrimEnd('\')
$bash = Join-Path $Msys2Root 'usr\bin\bash.exe'

if ($Msys2Root -ieq 'C:\msys64') {
    [Console]::Error.WriteLine("build.ps1: refusing to use C:\msys64; ContextCut builds only in its own MSYS2 (default D:\ContextCut\env\msys64).")
    exit 2
}
if (-not (Test-Path -LiteralPath $bash)) {
    [Console]::Error.WriteLine("build.ps1: no MSYS2 at '$Msys2Root' (missing usr\bin\bash.exe).")
    [Console]::Error.WriteLine("  Pass -Msys2Root <dir> or set CONTEXTCUT_MSYS2 to an MSYS2 install used only for ContextCut.")
    exit 2
}

# PowerShell 5.1 mangles quotes in inline bash commands, so always run the script file.
$env:MSYSTEM = 'UCRT64'
$env:MSYS2_PATH_TYPE = 'minimal'   # keep Windows PATH tools (e.g. user Python) out of configure
$env:CHERE_INVOKING = '1'
$bashArgs = @('-l', (($PSScriptRoot -replace '\\', '/') + '/build.sh'))
if ($SkipDeps) { $bashArgs += '--skip-deps' }
if ($Reconfigure) { $bashArgs += '--reconfigure' }
if ($ConfigureOnly) { $bashArgs += '--configure-only' }

$timer = [Diagnostics.Stopwatch]::StartNew()
& $bash @bashArgs
$code = $LASTEXITCODE
Write-Host ("build.ps1: exit {0} after {1:mm\:ss}" -f $code, $timer.Elapsed)
exit $code
