# DS_Projects

Личный портфель мелких утилит и экспериментов (Python, AutoHotkey, Cursor).  
Это не один большой продукт — **каждая папка = отдельный мини-проект**.

## С чего начать

1. Поставь **Python 3.11+** (лучше 3.13) и при необходимости **Git**.
2. Открой нужную папку по таблице ниже.
3. Поставь зависимости **только для этого проекта** (не обязательно всё сразу).
4. Секреты (API-ключи) — только в корневом `.env` (файл в `.gitignore`, в репо не класть).

Подробная инструкция по озвучке Cursor: [`Cursor_TTS/README.md`](Cursor_TTS/README.md).  
Список идей / бэклог: [`IDEAS.md`](IDEAS.md) (для себя и для ИИ в Cursor, не гайд «для гостей»).

---

## Структура репозитория

```
DS_Projects/
├── README.md                 ← ты здесь
├── IDEAS.md                  ← памятка идей
├── .env                      ← секреты (локально, не в git)
├── .gitignore
├── .cursor/                  ← хуки и правила Cursor
│   ├── hooks.json
│   ├── hooks/tts_after_response.py
│   └── rules/
├── Cursor_TTS/               ← озвучка ответов Agent
├── YouTube_Translator/       ← субтитры YouTube (GUI)
├── Channel_Translator/       ← массовый рип канала (зависит от YouTube_*)
├── Epub2txt/                 ← EPUB → TXT
├── Book_Parter/              ← мелочи для текста книг
├── DeepSeek_IA/              ← примеры запросов к DeepSeek API
└── for_Mount&blade2_…/       ← макросы AutoHotkey для игры
```

---

## Проекты: что это и какие библиотеки

| Папка | Зачем | Как запустить | Зависимости |
|-------|--------|---------------|-------------|
| **Cursor_TTS** | Озвучка ответов в Cursor (Edge / Silero), панель, хоткеи | Ярлык / `Start_TTS_Panel.vbs` или см. README внутри | `pip install -r Cursor_TTS/requirements.txt` → edge-tts, pygame, PyQt5, numpy, soundfile, omegaconf, ru-normalizr, torch. Плюс **AutoHotkey v1** для хоткеев. Хук Cursor: `.cursor/hooks.json` |
| **YouTube_Translator** | GUI: ссылка на ролик → субтитры (yt-dlp) | `python YouTube_Translator/Subtitle_App.py` | **PyQt5**, системный **yt-dlp** в PATH. Опционально: `faster-whisper` для `whisper_transcribe.py` |
| **Channel_Translator** | Список видео канала → пакетная обработка | `python Channel_Translator/channel_ripper.py` | **yt-dlp**; импортирует модуль из `YouTube_Translator` (пути завязаны) |
| **Epub2txt** | Книга EPUB → чистый TXT | `python Epub2txt/epub2txt.py` | `pip install ebooklib` |
| **Book_Parter** | Убрать пустые строки из TXT и т.п. | `python Book_Parter/remove_empty_lines.py` | Стандартная библиотека Python |
| **DeepSeek_IA** | Скрипт запросов к DeepSeek | `python DeepSeek_IA/deepseek_python_….py` | `pip install openai python-dotenv`; ключ `DEEPSEEK_API_KEY` в `.env` |
| **for_Mount&blade2_…** | Макросы AHK (клики / автоматизация) | Открыть `.ahk` в **AutoHotkey v1** | AutoHotkey, без Python |

---

## Общее окружение

- Один Python на машину обычно хватает; для тяжёлого (torch / whisper) можно завести venv в папке проекта.
- **Не коммить:** `.env`, `__pycache__`, `*.exe`, логи (`tts_debug.log`, `debug-*.log`), pid-файлы, флаг `TTS_OFF`.
- Корневого `requirements.txt` на всё репо нет намеренно: проекты разные, зависимости ставятся точечно.

---

## Бэкап: git vs папка «архив» на рабочем столе

**Источник правды — этот репозиторий + `git commit` / `git push`.**  
Копия `DS_Projects - архив` на рабочем столе быстро устаревает: день поработал — архив уже не тот, а обновлять руками лень (и правильно).

Практичный режим:

1. Закончил фичу → **коммит** (и при желании push на GitHub).
2. Архив на рабочем столе — **редко** (раз в месяц / перед большим риском), не каждый вечер.
3. Или вообще убрать архив и жить на git: откат = старый коммит, а не «какая копия свежее?».

ZIP имеет смысл только как разовый снимок «на флешку / перед сносом Windows».

---

## Для людей, которые смотрят репо

- Это учебный / pet-портфель, код разного возраста и аккуратности.
- Самый «собранный» кусок с нормальной шпаргалкой сейчас — **Cursor_TTS**.
- Вопросы по идеям и планам — смотри `IDEAS.md`, не жди там install-инструкций.
