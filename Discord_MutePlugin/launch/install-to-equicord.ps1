# Copy voiceMuteSlots userplugin into Equicord source tree.
# Usage:
#   $env:EQUICORD_SRC = "C:\path\to\Equicord"
#   .\launch\install-to-equicord.ps1
#   cd $env:EQUICORD_SRC; pnpm build; pnpm inject

param(
    [string]$EquicordSrc = $env:EQUICORD_SRC
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SrcPlugin = Join-Path $ProjectRoot "src\voiceMuteSlots"
$DestRoot = if ($EquicordSrc) { Join-Path $EquicordSrc "src\userplugins\voiceMuteSlots" } else { $null }

if (-not $DestRoot) {
    Write-Host "Set EQUICORD_SRC or pass -EquicordSrc to your Equicord clone path." -ForegroundColor Yellow
    Write-Host "Example: `$env:EQUICORD_SRC = 'C:\dev\Equicord'; .\launch\install-to-equicord.ps1"
    exit 1
}

if (-not (Test-Path $SrcPlugin)) {
    Write-Error "Plugin source not found: $SrcPlugin"
}

New-Item -ItemType Directory -Force -Path (Split-Path $DestRoot) | Out-Null
# Always wipe dest first — otherwise Copy-Item nests voiceMuteSlots/voiceMuteSlots/
if (Test-Path $DestRoot) {
    Remove-Item -Recurse -Force $DestRoot
}
New-Item -ItemType Directory -Force -Path $DestRoot | Out-Null
Copy-Item -Force (Join-Path $SrcPlugin "*") $DestRoot

$nested = Join-Path $DestRoot "voiceMuteSlots"
if (Test-Path $nested) {
    Write-Host "WARN: nested folder detected, flattening..." -ForegroundColor Yellow
    Copy-Item -Force (Join-Path $nested "*") $DestRoot
    Remove-Item -Recurse -Force $nested
}

$listen = Join-Path $DestRoot "voiceListen.ts"
if (-not (Test-Path $listen)) {
    Write-Error "Install failed — voiceListen.ts missing at $DestRoot"
}
if (Select-String -Path $listen -Pattern "но нет слота словом" -Quiet) {
    Write-Error "OLD voiceListen.ts still present — wipe failed"
}

Write-Host "Copied -> $DestRoot" -ForegroundColor Green
Write-Host "Next: cd `"$EquicordSrc`"; pnpm build; then inject (close Discord first)"
