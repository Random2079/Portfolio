# YouTube Translator

GUI: вставил ссылку на ролик YouTube → скачал/достал субтитры (через **yt-dlp**).

Интерфейс: **CustomTkinter** (старый PyQt — `Subtitle_App_qt_backup.py`).

## Запуск

```powershell
cd YouTube_Translator
pip install -r requirements.txt
# yt-dlp должен быть в PATH (уже в requirements) или: winget install yt-dlp
python Subtitle_App.py
```

Опционально сборка exe: `pyinstaller --noconfirm Subtitle_App.spec`

## Что получается в папке ролика

| Файл | Зачем |
|------|--------|
| `0_весь_текст_для_буфера.txt` | Чистый текст (и в буфер Ctrl+V) |
| `1_текст_с_таймкодами.txt` | Фразы вида `[mm:ss] текст` — прыжок к моменту на видео |
| `часть_ru_1.txt` … | Куски чистого текста, если очень длинно |

Склейка таймкодов: соседние куски SRT объединяются при паузе &lt; 1.5 с и длине фразы ≲ 120 символов (не word-level).

## Файлы проекта

| Файл | Зачем |
|------|--------|
| `Subtitle_App.py` | Окно CTk, валидация ссылки, вызов yt-dlp |
| `Subtitle_App_qt_backup.py` | Старый GUI на PyQt5 (бэкап) |
| `whisper_transcribe.py` | Локальная расшифровка аудио → `.srt` / `.txt` (**faster-whisper**) |
| `Subtitle_App.spec` | Сборка в exe |
| `requirements.txt` | customtkinter, yt-dlp |

## Зависимости

- Обязательно: **customtkinter**, **yt-dlp**
- Для Whisper-скрипта: `pip install faster-whisper`
