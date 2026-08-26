# Хвост лога STT (что реально услышал vosk)
$Project = Split-Path -Parent $PSScriptRoot
$Log = Join-Path $Project "stt\logs\stt.log"
if (-not (Test-Path $Log)) {
    Write-Host "Лога пока нет: $Log" -ForegroundColor Yellow
    Write-Host "Запусти launch\Start-VoiceStt.ps1 и скажи что-нибудь с Shift+K"
    exit 1
}
Get-Content $Log -Tail 40 -Wait
