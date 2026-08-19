# Portfolio — Тё Ян (Python / automation)

**Ищу:** junior / стажировку / remote или гибрид — Python, автоматизация, утилиты, работа с API и данными.  
**Стек:** Python 3.11+, CustomTkinter / PyQt, yt-dlp, REST API, AutoHotkey, git.  
**Локация:** Сургут · готов к удалёнке · англ. C1.

Это репозиторий pet-проектов: небольшие рабочие утилиты «под себя», не учебный hello-world.

---

## С чего смотреть (для рекрутера / тимлида)

| Приоритет | Проект | За 15 секунд |
|-----------|--------|----------------|
| **1. Основной проект** | [**YouTube_Translator**](YouTube_Translator/) | GUI: ссылка на YouTube → субтитры + текст + таймкоды (`yt-dlp`, CustomTkinter). Есть fallback через Whisper. |
| **2** | [**Cursor_TTS**](Cursor_TTS/) | Озвучка ответов IDE: очередь, панель, Kokoro / Qwen, хоткеи. |
| **3 (опц.)** | [**DeepSeek_IA**](DeepSeek_IA/) | Черновой CLI-клиент к DeepSeek API (в разработке, не готовый продукт). |

Остальное — вспомогательные скрипты (EPUB→TXT, макросы игр) и черновики.

**Прямая ссылка на основной проект:**  
https://github.com/Random2079/Portfolio/tree/main/YouTube_Translator

---

## Коротко обо мне

- Пишу утилиты, чтобы не кликать руками: парсинг, GUI, API, локальные пайплайны.  
- Довожу до рабочего состояния у себя на машине (запуск, README, зависимости по папкам).  
- Без коммерческого опыта в штате — есть законченные pet-проекты и готовность разбирать чужой код / чинить по симптомам.

---

## Как запустить любой проект

1. Python **3.11+** (лучше 3.13), Git.  
2. Открой папку проекта → `pip install -r requirements.txt` (если есть).  
3. Секреты только в корневом `.env` (в git не попадает).

---

## Структура репозитория

```
Portfolio/
├── README.md                 ← ты здесь
├── PROJECTS.md               ← карта проектов
├── HH_SNIPPET.md             ← текст для отклика на HH (копипаст)
├── YouTube_Translator/       ← ★ основной проект: субтитры YouTube
├── Cursor_TTS/               ← озвучка Cursor
├── Channel_Translator/       ← пакетный обход канала
├── DeepSeek_IA/              ← черновой пример LLM API
├── Epub2txt/ · Book_Parter/  ← мелкие текстовые утилиты
├── MountBlade2_AHK/          ← макросы AHK (не для резюме)
└── …
```

Полная таблица «что / зачем / зависимости» — ниже и в [`PROJECTS.md`](PROJECTS.md).

---

## Проекты: что это и какие библиотеки

| Папка | Зачем | Как запустить | Зависимости |
|-------|--------|---------------|-------------|
| **YouTube_Translator** | GUI: ссылка → субтитры + таймкоды | `python YouTube_Translator/Subtitle_App.py` | customtkinter, **yt-dlp** в PATH; опц. faster-whisper |
| **Cursor_TTS** | Озвучка ответов Cursor (Kokoro / Qwen) | `Start_TTS_Panel.vbs` / см. README | см. `Cursor_TTS/requirements.txt`, AutoHotkey v1 |
| **Channel_Translator** | Список видео канала → пакетная обработка | `python Channel_Translator/channel_ripper.py` | yt-dlp + модули YouTube_Translator |
| **DeepSeek_IA** | Черновой CLI для запросов к DeepSeek API | см. README в папке | openai, python-dotenv |
| **Epub2txt** | EPUB → TXT | `python Epub2txt/epub2txt.py` | ebooklib |
| **Book_Parter** | Мелкие правки TXT | см. папку | stdlib |
| **MountBlade2_AHK** | Макросы M&B II | AutoHotkey v1 | без Python |

---

## Заметки по репозиторию

- Учебный / pet-портфель: код разного возраста; витрина для найма — **YouTube_Translator** и **Cursor_TTS**.  
- Корневого `requirements.txt` нет намеренно: зависимости ставятся точечно по папкам.  
- Не коммитить: `.env`, `__pycache__`, `*.exe`, логи, pid-файлы.

Бэклог идей для себя: [`IDEAS.md`](IDEAS.md) (не обязательно читать при оценке кандидата).
