# YouTube Translator (Subtitle Ripper Pro)

Скачивание субтитров YouTube, встроенный плеер с таймкодами, ИИ-разбор (DeepSeek).

**Статус:** рабочий pet-проект.  
**Стек:** Python · **PySide6 + QtWebEngine** · yt-dlp · (опц.) faster-whisper.

Подробное ТЗ и карточки для агента → **[docs/TZ.md](docs/TZ.md)** · промпт → [docs/PROMPT_FOR_AGENT.md](docs/PROMPT_FOR_AGENT.md).

---

## Структура

```
YouTube_Translator/
├── Subtitle_App.py       # GUI + плеер + скачивание + закладки
├── ai_analyze.py         # ИИ-разбор (инвест / обычный)
├── timecode_player.py    # player.html / marks
├── ui_motion.py          # hover / busy pulse
├── launch.vbs / launch/  # запуск без консоли
├── requirements.txt
├── bookmarks.json
├── dist/                 # субтитры_<title> [youtubeId]/
├── yt_profile/           # устар.: мигрирует в %LOCALAPPDATA%\SubtitleRipperPro\
└── docs/                 # ТЗ, parts (не смешивать с .py)
```

WebEngine-профили (куки YouTube/закладки) живут в `%LOCALAPPDATA%\SubtitleRipperPro\`, не в OneDrive — иначе SearchIndexer разгоняется на тысячах мелких файлов Chromium.

Бэкап старого CTk/Qt: `Subtitle_App_qt_backup.py` / тонкие backup-файлы — не боевой путь.

---

## Быстрый старт

```powershell
cd YouTube_Translator
pip install -r requirements.txt
# боевой GUI нужен PySide6 (+ QtWebEngine); доустанови при ImportError
python Subtitle_App.py
# или: wscript launch.vbs
```

1. URL → **Скачать** → папка в `dist/`.  
2. **Плеер** → YouTube + сайдбар.  
3. **✨ ИИ** — разбор **текущего** ролика в WebView (субы из `dist/` или авто-скачивание → DeepSeek).  
4. **📥** — только субы текущего URL без ИИ.  
5. **🎵** — MP3 в `Music\YouTube_DL`.

Опционально exe: `pyinstaller --noconfirm Subtitle_App.spec` (только по нужде).

---

## Результат в папке ролика

| Файл | Зачем |
|------|--------|
| `0_весь_текст_для_буфера.txt` | Чистый текст |
| `1_текст_с_таймкодами.txt` | `[mm:ss] фраза` |
| `ai_analysis.json` | Сохранённый ИИ-разбор |
| `player.html` | Legacy HTML-плеер |

Родительский обзор: [README.md](../README.md) · идеи: [IDEAS.md](../IDEAS.md).
