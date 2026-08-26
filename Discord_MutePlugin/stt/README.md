# Offline STT for VoiceMuteSlots (Vosk)

Не Google. Не нужен интернет для распознавания.

## Запуск

```powershell
.\launch\Start-VoiceStt.ps1
```

или

```powershell
& "C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_VoiceMute\.venv\Scripts\python.exe" `
  "C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_MutePlugin\stt\vosk_daemon.py"
```

Слушает: `http://127.0.0.1:39281`

- `GET /health`
- `POST /listen/start` — начать писать микрофон
- `POST /listen/stop` — стоп, `{ "transcript": "..." }`

## Движок STT

Сейчас по умолчанию **`faster-whisper`** (`engine: "whisper"`, модель `small`, CPU int8).

| | Совместимость | Качество RU | Скорость на 1–2с PTT |
|--|--|--|--|
| **whisper small** (сейчас) | тот же HTTP :39281 | сильно лучше vosk-small | ~0.3–1.5с на CPU |
| vosk-small + grammar | отлично | слабо в шуме | мгновенно |
| vosk-ru-0.42 | отлично | средне+ | быстро |
| whisper medium/turbo | нужно GPU/дольше | ещё лучше | тяжелее |

Вернуть Vosk: в `stt_config.json` поставь `"engine": "vosk"` и перезапусти демон.

## Логи — что именно услышал

После каждого Shift+K:

1. **HUD в Discord** — текст Whisper + rms
2. **Файл** `stt/logs/last_heard.json`
3. **WAV** `stt/logs/clips/ptt_*.wav`
4. `.\launch\Show-LastHeard.ps1`
5. Discord: `/stt-last`

Модель Whisper качается при первом старте демона (HuggingFace).
Vosk-модель (fallback): `stt/models/vosk-model-small-ru-0.22`

## Логи

**Файл:** `stt/logs/stt.log` — каждый Shift+K: partial, final, transcript, peak_rms, mic.

```powershell
.\launch\Show-SttLog.ps1
```

В Discord: **Ctrl+Shift+I** → Console → `[VoiceMuteSlots] STT: ...`

## Настройка микрофона

`stt/stt_config.json`:

- `"gain": 2.2` — усиление (как в старом Discord_VoiceMute)
- `"input_device": 1` — индекс mic (список: `GET http://127.0.0.1:39281/devices`)
- `"use_grammar": true` — словарь «замутить первого» (не обрезает на «за»)

Тест без Discord:

```powershell
& "...\Discord_VoiceMute\.venv\Scripts\python.exe" stt\test_mic.py
```

## Другие движки распознавания

| Движок | Плюсы | Минусы |
|--------|-------|--------|
| **Vosk small + grammar** (сейчас) | офлайн, быстро, ~45 MB | иногда криво без grammar |
| **Vosk ru-0.42** (больше) | точнее | ~1.5 GB, скачать отдельно |
| **faster-whisper** | очень точно | тяжёлый, медленнее на stop |
| **Google STT в Discord** | — | не работает в Electron |

Whisper можно добавить вторым engine в daemon — скажи, если Vosk с grammar всё ещё плохо.
