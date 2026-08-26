# Start STT daemon for VoiceMuteSlots (vosk / whisper / google)
param(
    [switch]$ForceRestart
)
$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
$Daemon = Join-Path $Project "stt\vosk_daemon.py"
$SttDir = Join-Path $Project "stt"
$Py = "C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_VoiceMute\.venv\Scripts\python.exe"
$Health = "http://127.0.0.1:39281/health"

if (-not (Test-Path $Py)) {
    Write-Host "Python venv not found: $Py" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Daemon)) {
    Write-Host "Daemon not found: $Daemon" -ForegroundColor Red
    exit 1
}

function Get-HealthJson {
    try {
        $r = Invoke-WebRequest -Uri $Health -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { return $r.Content }
    } catch { }
    return $null
}

function Stop-SttDaemon {
    for ($round = 1; $round -le 3; $round++) {
        $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -match "vosk_daemon\.py" })
        if (-not $procs.Count) { break }
        foreach ($p in $procs) {
            Write-Host "Stopping PID $($p.ProcessId) (round $round)…" -ForegroundColor Yellow
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Milliseconds (400 * $round)
    }
    # Last resort: whoever still owns :39281
    try {
        $conns = Get-NetTCPConnection -LocalPort 39281 -State Listen -ErrorAction SilentlyContinue
        foreach ($c in @($conns)) {
            if ($c.OwningProcess) {
                Write-Host "Killing port 39281 owner PID $($c.OwningProcess)…" -ForegroundColor Yellow
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
    } catch { }
    Start-Sleep -Milliseconds 400
    $left = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "vosk_daemon\.py" })
    if ($left.Count) {
        Write-Host "WARN: still $($left.Count) vosk_daemon after kill" -ForegroundColor Red
    }
}

$existing = Get-HealthJson
if ($existing -and -not $ForceRestart) {
    Write-Host "STT already running on :39281" -ForegroundColor Green
    Write-Host $existing
    exit 0
}

if ($existing -or $ForceRestart) {
    Stop-SttDaemon
}

Write-Host "Starting STT daemon…"
$errLog = Join-Path $SttDir "logs\daemon_stderr.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $errLog) | Out-Null
if (Test-Path $errLog) {
    try { Remove-Item $errLog -Force -ErrorAction Stop }
    catch {
        # previous daemon may still hold the handle briefly
        $errLog = Join-Path $SttDir ("logs\daemon_stderr_{0}.txt" -f (Get-Date -Format "HHmmss"))
        Write-Host "stderr locked — logging to $errLog" -ForegroundColor Yellow
    }
}

Start-Process -FilePath $Py `
    -ArgumentList "`"$Daemon`"" `
    -WorkingDirectory $SttDir `
    -WindowStyle Minimized `
    -RedirectStandardError $errLog `
    -RedirectStandardOutput (Join-Path $SttDir "logs\daemon_stdout.txt")

$ok = $null
$maxWait = if ($env:STT_WAIT_SEC) { [int]$env:STT_WAIT_SEC } else { 90 }
for ($i = 0; $i -lt $maxWait; $i++) {
    Start-Sleep -Seconds 1
    $ok = Get-HealthJson
    if ($ok) { break }
    if (($i + 1) % 10 -eq 0) {
        Write-Host "Waiting for model… $($i + 1)s / ${maxWait}s"
    }
}

if ($ok) {
    # Note: NeMo/torch may show 2 python processes with vosk_daemon in cmdline —
    # do NOT kill the "non-owner"; that can tear down the whole tree.
    $n = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "vosk_daemon\.py" }).Count
    Write-Host "OK ($n vosk_daemon process(es)): $ok" -ForegroundColor Green
    exit 0
}

Write-Host "Daemon health check failed after start." -ForegroundColor Red
if (Test-Path $errLog) {
    Write-Host "--- stderr ---" -ForegroundColor Yellow
    Get-Content $errLog -ErrorAction SilentlyContinue | Select-Object -Last 40
}
exit 1
