# Build sibling React UI into dist/ (served by FastAPI at /app/).
$ErrorActionPreference = "Stop"
$pn = Split-Path $PSScriptRoot -Parent
$react = [IO.Path]::GetFullPath((Join-Path $pn "..\react_Portfolio_News"))
if (-not (Test-Path (Join-Path $react "package.json"))) {
    Write-Error "Not found: $react"
}
Set-Location $react
if (-not (Test-Path "node_modules")) { npm install }
npm run build
Write-Host "OK → $react\dist  (open http://127.0.0.1:8765/app/ after serve)"
