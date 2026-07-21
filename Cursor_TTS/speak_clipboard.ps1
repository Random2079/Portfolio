# Озвучка текста (Windows SAPI).
# Запуск: speak_clipboard.ps1
#        speak_clipboard.ps1 -Path "C:\temp\file.txt"
param(
    [string]$Path = ""
)

Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speak.Rate = 1
$speak.Volume = 100

if ($Path -and (Test-Path -LiteralPath $Path)) {
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
} else {
    $text = Get-Clipboard -Raw
}

if ([string]::IsNullOrWhiteSpace($text)) {
    exit 1
}

# Лёгкая чистка markdown
$text = [regex]::Replace($text, '```[\s\S]*?```', ' блок кода ')
$text = [regex]::Replace($text, '`([^`]+)`', '$1')
$text = [regex]::Replace($text, '\[([^\]]+)\]\([^)]+\)', '$1')
$text = [regex]::Replace($text, '[#*_>~]+', ' ')
$text = [regex]::Replace($text, '\s+', ' ').Trim()

if ([string]::IsNullOrWhiteSpace($text)) {
    exit 1
}

$speak.Speak($text)
