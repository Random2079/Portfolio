# Прописывает ОДИН глобальный TTS-хук в %USERPROFILE%\.cursor\
# Работает во всех проектах Cursor (старых и новых), пока открыта панель.
#
# Запуск из корня клона:
#   powershell -ExecutionPolicy Bypass -File scripts\install_cursor_hook.ps1
#
# Cursor сам хуки из репозитория «навсегда» не ставит — этот скрипт обязателен
# один раз на машину (или после переезда папки TTS).

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SrcHook = Join-Path $RepoRoot ".cursor\hooks\tts_after_response.py"
$UserCursor = Join-Path $env:USERPROFILE ".cursor"
$UserHooksDir = Join-Path $UserCursor "hooks"
$UserHooksJson = Join-Path $UserCursor "hooks.json"
$DstHook = Join-Path $UserHooksDir "tts_after_response.py"
$DstCmd = Join-Path $UserHooksDir "cursor_tts_hook.cmd"
$RootMarker = Join-Path $UserHooksDir "tts_root.txt"

if (-not (Test-Path $SrcHook)) {
    throw "Не найден шаблон хука: $SrcHook"
}

New-Item -ItemType Directory -Force -Path $UserHooksDir | Out-Null

# Канонический путь к клону — читает глобальный хук (и можно править вручную).
[System.IO.File]::WriteAllText($RootMarker, $RepoRoot, [System.Text.UTF8Encoding]::new($false))

# Глобальный .py: TTS_ROOT из tts_root.txt (не от __file__), чтобы не зависеть от project hooks.
$hookBody = @'
"""
Глобальный Cursor TTS hook (user-level).
Ставится scripts/install_cursor_hook.ps1 → ~/.cursor/hooks/
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
_ROOT_FILE = _HOOKS_DIR / "tts_root.txt"


def _load_tts_root() -> Path:
    if _ROOT_FILE.is_file():
        raw = _ROOT_FILE.read_text(encoding="utf-8").strip().strip('"')
        if raw:
            return Path(raw)
    raise RuntimeError(
        f"Нет пути к Cursor TTS: создай {_ROOT_FILE} одной строкой "
        r"(например C:\path\to\Cursor-TTS) или перезапусти install_cursor_hook.ps1"
    )


TTS_ROOT = _load_tts_root()
OFF_FLAG = TTS_ROOT / "TTS_OFF"
PANEL_ACTIVE_FLAG = TTS_ROOT / "TTS_PANEL_ACTIVE"
HOOK_DEDUP_DIR = Path(tempfile.gettempdir()) / "cursor_tts_hook_dedup"
LOG_FILE = Path(tempfile.gettempdir()) / "cursor_tts_hook.log"

sys.path.insert(0, str(TTS_ROOT))
try:
    from tts_debug import log_clean_result
except ImportError:
    def log_clean_result(raw_preview: str, cleaned: str) -> None:
        return None


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {message}\n")


def claim_generation(generation_id: str, conversation_id: str = "") -> bool:
    gid = (generation_id or "").strip()
    if not gid:
        return True
    try:
        HOOK_DEDUP_DIR.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for stale in HOOK_DEDUP_DIR.glob("*.claim"):
            try:
                if now - stale.stat().st_mtime > 600:
                    stale.unlink(missing_ok=True)
            except OSError:
                pass
        key = f"{conversation_id[:32]}_{gid[:64]}".replace("/", "_")
        path = HOOK_DEDUP_DIR / f"{key}.claim"
        try:
            fd = path.open("x", encoding="utf-8")
            fd.write(str(now))
            fd.close()
            return True
        except FileExistsError:
            return False
    except OSError:
        return True


def read_hook_payload(raw: str) -> dict:
    log(f"stdin chars={len(raw)} preview={raw[:120]!r}")
    if not raw.strip():
        raise ValueError("stdin empty")
    raw = raw.lstrip("\ufeff").strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("payload is not an object")
    return data


def read_last_assistant_message(path: Path) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("role") != "assistant":
            continue
        content = item.get("message", {}).get("content", [])
        text_parts = [
            part.get("text", "")
            for part in content
            if part.get("type") == "text"
        ]
        text = "\n".join(part for part in text_parts if part.strip())
        if text:
            return text
    return ""


_MOJIBAKE_MARKERS = ("Рµ", "Рѕ", "РЅ", "СЂ", "СЃ", "Рё", "РІ", "Р°", "вЂ")


def fix_mojibake(text: str) -> str:
    if not any(marker in text for marker in _MOJIBAKE_MARKERS):
        return text
    out = []
    for line in text.split("\n"):
        try:
            out.append(line.encode("cp1251").decode("utf-8"))
        except UnicodeError:
            out.append(line)
    return "\n".join(out)


def extract_text(data: dict) -> str:
    text = str(data.get("text") or "").strip()
    if text:
        text = fix_mojibake(text)
        log(f"loaded assistant text from payload: chars={len(text)}")
        return text
    transcript = data.get("transcript_path")
    if transcript:
        path = Path(str(transcript))
        if path.is_file():
            text = read_last_assistant_message(path)
            if text:
                log(f"loaded assistant text from transcript: chars={len(text)}")
                return text
    return str(data.get("text") or "")


MAX_SPEECH_CHARS = 12000


def enqueue_auto(text: str, data: dict) -> None:
    from speak_edge import daemon_alive, ensure_daemon, panel_active, send_command

    if not panel_active():
        log("TTS panel not running — skip auto")
        return
    if not daemon_alive():
        ensure_daemon()
    payload = {
        "cmd": "enqueue_auto",
        "entry": {
            "text": text,
            "conversation_id": str(data.get("conversation_id") or ""),
            "generation_id": str(data.get("generation_id") or ""),
            "source": str(data.get("hook_event_name") or "afterAgentResponse"),
        },
    }
    reply = send_command(payload, timeout=5.0)
    if not reply.get("ok"):
        raise RuntimeError(str(reply.get("error") or "enqueue_auto failed"))
    log(
        "TTS auto queued: "
        f"chars={len(text)} conv={payload['entry']['conversation_id'][:12]} "
        f"gen={payload['entry']['generation_id'][:12]} "
        f"source={payload['entry']['source']}"
    )


def main() -> int:
    log("Hook invoked (user-global)")
    from speak_edge import daemon_alive, panel_active

    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    raw_stdin = sys.stdin.read()

    if not raw_stdin.strip():
        log("stdin empty — stop/no-op")
        if daemon_alive():
            try:
                from speak_edge import send_command
                send_command({"cmd": "stop"}, timeout=2.0)
                log("hook empty stdin -> daemon stop")
            except Exception as error:
                log(f"hook empty stdin stop failed: {type(error).__name__}: {error}")
        return 0

    if OFF_FLAG.exists():
        log("TTS disabled by TTS_OFF")
        return 0

    if not panel_active():
        log("TTS panel not running — skip hook")
        if daemon_alive():
            try:
                from speak_edge import stop_daemon
                stop_daemon(force=True)
                log("orphan daemon stopped (panel closed)")
            except Exception as error:
                log(f"orphan daemon stop failed: {type(error).__name__}: {error}")
        return 0

    try:
        data = read_hook_payload(raw_stdin)
    except Exception as error:
        log(f"Payload failed: {type(error).__name__}: {error}")
        return 0

    event = str(data.get("hook_event_name") or "")
    status = str(data.get("status") or "")
    conv = str(data.get("conversation_id") or "")
    gen = str(data.get("generation_id") or "")

    if event == "stop":
        if status.strip().lower() == "completed":
            log(f"hook stop ignored (status={status}) — keep TTS playback")
            return 0
        try:
            from speak_edge import send_command
            if daemon_alive():
                send_command({"cmd": "stop"}, timeout=2.0)
                log(f"hook stop -> daemon stop (status={status})")
        except Exception as error:
            log(f"hook stop failed: {type(error).__name__}: {error}")
        return 0

    if not claim_generation(gen, conv):
        log(f"Duplicate hook skipped gen={gen[:12]}")
        return 0

    text = extract_text(data).strip()
    log_clean_result(text[:200], text[:200])
    if len(text) < 8:
        log(f"Text too short: chars={len(text)}")
        return 0
    if len(text) > MAX_SPEECH_CHARS:
        text = text[:MAX_SPEECH_CHARS] + " … дальше слишком длинно, обрезано."
        log(f"Text capped at {MAX_SPEECH_CHARS} chars")

    try:
        enqueue_auto(text, data)
    except Exception as error:
        log(f"Speech failed: {type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

[System.IO.File]::WriteAllText($DstHook, $hookBody, [System.Text.UTF8Encoding]::new($false))

$cmdBody = @"
@echo off
setlocal
set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0tts_after_response.py"
"@
[System.IO.File]::WriteAllText($DstCmd, $cmdBody, [System.Text.UTF8Encoding]::new($false))

# hooks.json: только user-level. loop_limit ДОЛЖЕН быть null (не 0).
$config = @{
    version = 1
    hooks   = @{
        afterAgentResponse = @(
            @{
                command = "./hooks/cursor_tts_hook.cmd"
                timeout = 30
            }
        )
        stop = @(
            @{
                command    = "./hooks/cursor_tts_hook.cmd"
                timeout    = 30
                loop_limit = $null
            }
        )
    }
}

$json = $config | ConvertTo-Json -Depth 6
# PowerShell пишет null как null — ок. Уберём BOM.
[System.IO.File]::WriteAllText($UserHooksJson, $json, [System.Text.UTF8Encoding]::new($false))

# Project hooks пустые — иначе Cursor мержит второй конфиг и снова ломается.
$emptyHooks = '{ "version": 1, "hooks": {} }'
foreach ($projectHooks in @(
        (Join-Path $RepoRoot ".cursor\hooks.json"),
        (Join-Path (Split-Path $RepoRoot -Parent) ".cursor\hooks.json")
    )) {
    $parent = Split-Path $projectHooks -Parent
    if (Test-Path $parent) {
        [System.IO.File]::WriteAllText($projectHooks, $emptyHooks, [System.Text.UTF8Encoding]::new($false))
    }
}

Write-Host "OK: global TTS hook installed"
Write-Host "  hooks.json : $UserHooksJson"
Write-Host "  script     : $DstHook"
Write-Host "  TTS root   : $RepoRoot"
Write-Host ""
Write-Host "Дальше: перезапусти Cursor (или дождись reload hooks),"
Write-Host "открой панель Start_TTS_Panel.vbs — авто-озвучка во ВСЕХ чатах."
