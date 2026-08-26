# Что услышал STT в последний Shift+K
$Project = Split-Path -Parent $PSScriptRoot
$Last = Join-Path $Project "stt\logs\last_heard.json"
$Clips = Join-Path $Project "stt\logs\clips"

if (-not (Test-Path $Last)) {
    Write-Host "Ещё нет last_heard.json — скажи что-нибудь с Shift+K" -ForegroundColor Yellow
    exit 1
}

Write-Host "==== last_heard.json ====" -ForegroundColor Cyan
Get-Content $Last -Encoding UTF8
Write-Host ""

try {
    $j = Invoke-RestMethod "http://127.0.0.1:39281/last" -TimeoutSec 2
    Write-Host "==== daemon /last ====" -ForegroundColor Cyan
    $j | ConvertTo-Json -Depth 5
} catch {
    Write-Host "(daemon не отвечает на /last — ок, смотри файл выше)" -ForegroundColor DarkYellow
}

if (Test-Path $Clips) {
    $wav = Get-ChildItem $Clips -Filter "*.wav" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($wav) {
        Write-Host ""
        Write-Host "Последний WAV (послушай в проводнике):" -ForegroundColor Green
        Write-Host $wav.FullName
        Start-Process explorer.exe -ArgumentList "/select,$($wav.FullName)"
    }
}
