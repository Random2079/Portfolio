# Hooks в репозитории

**Важно:** Cursor не включает авто-озвучку «сам из git clone».

Один раз на машине:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_cursor_hook.ps1
```

Скрипт пишет **user-level** хук:

- `%USERPROFILE%\.cursor\hooks.json`
- `%USERPROFILE%\.cursor\hooks\cursor_tts_hook.cmd`
- `%USERPROFILE%\.cursor\hooks\tts_after_response.py`
- `%USERPROFILE%\.cursor\hooks\tts_root.txt` ← путь к этому клону

`hooks.json` в репо специально пустой: project-hooks + user-hooks = двойной вызов и поломки (`loop_limit: 0`).

Не добавляй сюда `afterAgentResponse` / `stop` для TTS.
