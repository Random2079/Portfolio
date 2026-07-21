# YouTube Translator

GUI: вставил ссылку на ролик YouTube → скачал/достал субтитры (через **yt-dlp**).

## Запуск

```powershell
cd YouTube_Translator
pip install PyQt5
# yt-dlp должен быть в PATH: winget/pip install yt-dlp
python Subtitle_App.py
```

Опционально сборка exe: `Subtitle_App.spec` (PyInstaller).

## Файлы

| Файл | Зачем |
|------|--------|
| `Subtitle_App.py` | Окно PyQt5, валидация ссылки, вызов yt-dlp |
| `whisper_transcribe.py` | Локальная расшифровка аудио → `.srt` / `.txt` (**faster-whisper**) |
| `Subtitle_App.spec` | Сборка в exe |

## Зависимости

- Обязательно: **PyQt5**, **yt-dlp**
- Для Whisper-скрипта: `pip install faster-whisper`
