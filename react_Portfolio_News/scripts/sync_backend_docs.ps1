$ErrorActionPreference = "Stop"

$reactRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path (Split-Path -Parent $reactRoot) "Portfolio_News"
$targetRoot = Join-Path $reactRoot "docs\backend"
$targetDocs = Join-Path $targetRoot "docs"

if (-not (Test-Path (Join-Path $backendRoot "MAP.md"))) {
    throw "Portfolio_News sibling not found: $backendRoot"
}

New-Item -ItemType Directory -Force -Path $targetDocs | Out-Null
Copy-Item (Join-Path $backendRoot "MAP.md") (Join-Path $targetRoot "MAP.md") -Force
Copy-Item (Join-Path $backendRoot "README.md") (Join-Path $targetRoot "BACKEND_README.md") -Force
Copy-Item (Join-Path $backendRoot "docs\*") $targetDocs -Recurse -Force

@'
# Generated backend documentation mirror

Do not edit files in this folder. Source of truth:
`../Portfolio_News/MAP.md` and `../Portfolio_News/docs/`.

Refresh from `react_Portfolio_News`:
`npm run docs:sync`
'@ | Set-Content (Join-Path $targetRoot "_GENERATED.md") -Encoding UTF8

Write-Host "Backend docs synced to docs/backend"
