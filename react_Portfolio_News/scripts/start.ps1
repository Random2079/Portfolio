$ErrorActionPreference = "Stop"

$reactRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path (Split-Path -Parent $reactRoot) "Portfolio_News"

& (Join-Path $PSScriptRoot "sync_backend_docs.ps1")

Push-Location $reactRoot
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) {
        throw "React build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "Portfolio News is already running:"
    Write-Host "  React:  http://127.0.0.1:8765/app/"
    Write-Host "  Backup: http://127.0.0.1:8765/"
    exit 0
}

Set-Location $backendRoot
Write-Host "Starting Python API + React /app/..."
Write-Host "Stop with Ctrl+C."
& python -m portfolio_news serve
exit $LASTEXITCODE
