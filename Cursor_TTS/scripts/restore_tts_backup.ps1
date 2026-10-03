# Restore TTS config from config_backups\<Stamp>\
param(
    [Parameter(Mandatory = $false)]
    [string]$Stamp = "2026-10-02_heard_ok"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root "config_backups\$Stamp"
if (-not (Test-Path -LiteralPath $Src)) {
    throw "Backup not found: $Src"
}

$files = @("tts_config.json", "reading_profiles.json", "pronunciations.json")
foreach ($name in $files) {
    $from = Join-Path $Src $name
    if (Test-Path -LiteralPath $from) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $Root $name) -Force
        Write-Host "restored $name"
    } else {
        Write-Host "skip missing $name"
    }
}

Write-Host "Done. In TTS Panel: Stop then Restart daemon (or toggle reading profile)."
Write-Host "Source: $Src"
