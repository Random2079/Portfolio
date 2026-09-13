# Handoff — Cursor TTS (2026-08-28)

Краткий контекст для нового чата.

## Репозиторий

**Standalone:** `Cursor_TTS/` — свой git, витрина на GitHub (`Random2079/Cursor-TTS` — создать remote и push).

Старый монорепо Portfolio (`DS_Projects`) — TTS можно не дублировать в README Portfolio или оставить ссылку на отдельный репо.

## Что это

Локальная озвучка ответов Cursor Agent: hook → `speak_edge.py` → `tts_daemon.py` (порт 47391) → Silero / Edge / Tera / Qwen. Панель: `TTS_Panel.py`, хоткеи: `hotkey_tts.ahk`.

## Хук после выделения в отдельный репо

- Код хука: `.cursor/hooks/tts_after_response.py` (ROOT = корень репо).
- Установка: `scripts/install_cursor_hook.ps1` → `%USERPROFILE%\.cursor\hooks.json`.
- Старый путь Portfolio: `DS_Projects/.cursor/hooks/tts_after_response.py` — **заменить** install-скриптом после перехода на клон.

## Фиксы сессии 2026-08-28

1. Пауза без озвучки — `TTS_PAUSED` на idle снимается.
2. «Прослушать» — disabled при `daemon_busy`.
3. Смена движка — `reboot_daemon()`, комбо блок + откат.

## Демо

| Файл | Роль |
|------|------|
| `docs/demo_151324.mp4` | В README, ~1.4 MB |
| `docs/screenshots/demo_151324_*.png` | Кадры в README |

## Открыто

- `text_prep`: « » → запятые вокруг названий
- `pronunciations.json`
- Unit-тесты контрактов Stop/warmup — частично
- Portfolio: ссылка на этот репо вместо вложенной папки

## Не коммитить

`.env`, `TTS_OFF`, `TTS_PAUSED`, pid, `_bench_*`, логи.
