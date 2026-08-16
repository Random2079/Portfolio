# Cursor TTS — шпаргалка

## Запуск

### Панель настроек (PyQt)

Двойной клик (без чёрного окна Python):

- ярлык на рабочем столе **Cursor TTS**
- или `Cursor_TTS/Start_TTS_Panel.vbs`
- или `Cursor_TTS/Start_TTS_Panel.bat`

Из терминала:

```powershell
cd Cursor_TTS
pip install -r requirements.txt
python TTS_Panel.py
```

В окне: авто, **движок**, голос, громкость, **пауза между кусками**, «Прослушать», **«Пауза»**, «Стоп».  
При открытии панели демон поднимается сам и **прогревает** текущий движок в фоне.  
Живой статус показывает: **загрузка модели / синтез N из M / играет N из M / очередь N**.  
Пишет в те же файлы, что хук и AHK (`TTS_OFF`, `tts_config.json`).

### Два движка

| Движок | Когда |
|--------|--------|
| **Kokoro-ru** | быстрый локальный (CPU), голоса Света / Маша / Дима; лучше Piper |
| **Micro wife (Qwen)** | лучшее качество на GPU; 5–15 с на фразу после прогрева |

В `tts_config.json`: `"engine": "kokoro"|"qwen"`,  
`"kokoro_voice": "sveta"`,  
`"micro_wife_design_file": "micro_wife/designs/02_soft_high_female.txt"`.

Подробнее про Qwen: [`micro_wife/README.md`](micro_wife/README.md).

### Kokoro-ru (один раз)

Нужен отдельный **Python 3.12** (пакет `kokoro` не ставится на 3.13):

```powershell
py -3.12 -m venv C:\Users\Home\.venvs\kokoro312
C:\Users\Home\.venvs\kokoro312\Scripts\python.exe -m pip install kokoro soundfile huggingface_hub ruaccent
# ассеты уже в C:\Users\Home\.kokoro_ru (или скачает worker)
```

Демон (любой Python) держит тёплый worker через `speak_kokoro.py` → `micro_wife/kokoro_worker.py`.

## Горячие клавиши

Нужен запущенный `hotkey_tts.ahk` (ярлык **Cursor TTS** и панель поднимают его сами).

- `Ctrl + Shift + T` — включить или выключить автоматическую озвучку.
- `Ctrl + Shift + P` — **пауза / продолжить** (очередь не сбрасывается).
  - Замирает **на том же слоге** («я долбо-» → дальше «еб»), не прыгает на следующее предложение.
  - Подсказка: **`TTS: PAUSED`** или **`TTS: PLAYING`**.
  - В панели кнопка краснеет и пишет **«НА ПАУЗЕ — жми = продолжить»**.
- `Ctrl + Shift + X` — полный **стоп**: речь и очередь (пауза тоже снимается).
- `Ctrl + Shift + S` — озвучить **выделенный** текст (сначала выдели мышкой).

Также кнопки **Пауза** и **Стоп** в панели.

Клиент вручную:

```powershell
python speak_edge.py --pause-toggle
python speak_edge.py --stop
```

## Как понять состояние

После `Ctrl + Shift + T` появляется подсказка (на английском — так AHK не ломает буквы):

- `TTS AUTO: ON` — следующие ответы будут озвучиваться.
- `TTS AUTO: OFF` — следующие ответы будут молчать.

Отключённое состояние хранится в пустом файле `TTS_OFF` (галочка в панели или
`Ctrl+Shift+T`). Пока панель открыта — OFF действует. **При закрытии или следующем
запуске панели** авто снова включается (дефолт ON), чтобы хук не «залипал» молча.
Горячая клавиша сама создаёт/удаляет файл — вручную трогать не нужно.

## Пауза между кусками (не тараторить)

В панели слайдер **Пауза** (мс между кусками). По умолчанию **350 ms**.
По референсам TTS: после `.!?` пауза длиннее (~1.4×), после `,;:` короче (~0.6×).
`0` = без паузы (как раньше, встык).

Это **не** то же самое, что кнопка «Пауза» / Ctrl+Shift+P (заморозка звука на месте, потом resume с того же слога).

После правки кода демона **закрытие панели само по себе не подхватывает новый код**:
процесс `tts_daemon.py` живёт на порту 47391. Открой панель заново (она делает warmup)
или вручную: `python speak_edge.py --restart-daemon --warmup`.

## Текст для озвучки

- Стрелки `->` / `=>` / `→` → «затем».
- Markdown-таблицы: «Столбцы: …», дальше строки отдельными предложениями (короткие куски).
- Блоки ` ```mermaid ` → «Есть схема, смотри в чате.»; обычный code fence → «Блок кода…».
- Максимум 6 строк таблицы вслух, остальное — «и ещё N».

## Установка (один раз)

```powershell
cd Cursor_TTS
pip install -r requirements.txt
```

Голос и **громкость (10–100%)** — в панели или в `tts_config.json`.

Длинные ответы читаются **частями**.

## Файлы

- `Cursor_TTS/TTS_Panel.py` — окно настроек (PyQt).
- `.cursor/hooks.json` — запускает TTS после ответа Agent.
- `.cursor/hooks/tts_after_response.py` — получает текст и запускает голос.
- `Cursor_TTS/text_prep.py` — подготовка текста + **ru-normalizr**.
- `Cursor_TTS/tts_daemon.py` — тёплый фоновый воркер (очередь, pause/resume, stop).
- `Cursor_TTS/speak_edge.py` — клиент к демону (имя историческое).
- `Cursor_TTS/speak_kokoro.py` + `micro_wife/kokoro_worker.py` — Kokoro-ru.
- `Cursor_TTS/micro_wife/speak_qwen.py` — Qwen / micro wife.
- `Cursor_TTS/tts_config.json` — движок / голос / пауза.
- `Cursor_TTS/hotkey_tts.ahk` — горячие клавиши.

Старые Edge / Silero / Piper из каталога убраны (скрипты на диске могут ещё лежать, демон их не зовёт).

## Если не работает

1. Перезапусти `hotkey_tts.ahk` (после смены хоткеев — обязательно).
2. Проверь, что авто включено через `Ctrl + Shift + T`.
3. Для ручной проверки: выдели текст → `Ctrl + Shift + S`.
4. Стоп: `Ctrl + Shift + X` или кнопка **Стоп** в панели.
5. Лог хука: `%TEMP%/cursor_tts_hook.log`.
6. **Отладка озвучки**:
   - `Cursor_TTS/tts_debug.log` — куски, ошибки
   - `Cursor_TTS/tts_last_clean.txt` — последний текст в голос  
   Ищи строки `CHUNK_FAIL`.
7. Kokoro: проверь venv `C:\Users\Home\.venvs\kokoro312` и ассеты `C:\Users\Home\.kokoro_ru`.
8. После смены кода демона: `python speak_edge.py --restart-daemon --warmup`.
