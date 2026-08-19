# IDEA-016 — Локальный плеер таймкодов (план)

## Цель

После прогона ролика в папке уже есть `1_текст_с_таймкодами.txt`. Сейчас прыжок по времени = новая вкладка Chrome (`youtu.be?t=`). Нужен **один** `player.html`: iframe YouTube + кнопки, клик = `seekTo` в том же окне.

Не платформа, не VS Code, не аккаунты. Видео не скачивать.

## Как устроено сейчас (не ломать)

Пайплайн в [`Subtitle_App.py`](../../YouTube_Translator/Subtitle_App.py):

1. `download_and_split` → папка `субтитры_<title> [<video_id>]` **рядом с cwd** (обычно `YouTube_Translator/`, не обязательно `dist/`).
2. `write_output_texts` пишет `0_весь_текст_для_буфера.txt` и `1_текст_с_таймкодами.txt` (`[mm:ss] фраза`).
3. GUI после успеха ищет папку через `find_output_folder(video_id)` и копирует буфер.

`player.html` кладём **в ту же папку**, формат имени папки не меняем. Миграцию в `dist/` в этот MVP не тащим.

## Решения (зафиксировано)

| Тема | Выбор |
|------|--------|
| HTML | Один файл, инлайн CSS/JS, без npm |
| ID ролика | Из имени папки `[...]` **или** аргумент `video_id` (в пайплайне id уже есть — передаём явно, парсер имени — запасной) |
| Прореживание кнопок | Шаг **25 сек**: брать фразу, если `t >= last_t + 25` (первая всегда). Заголовок кнопки — обрезка фразы ~60 символов |
| Полезные метки | Если есть `метки.txt` или `highlights.json` — блок сверху; иначе блок скрыт. Формат: `mm:ss \| заголовок` (JSON: `[{"t":"mm:ss","title":"..."}]`) |
| file:// | Сначала пробовать открыть файл. Если IFrame API молчит — в README: `python -m http.server` из папки ролика. Отдельный демон в GUI **не** обязателен |
| GUI | После записи таймкодов сразу писать `player.html`. Кнопка **«Плеер»** (рядом со Скачать): открыть `player.html` через `os.startfile` если папка найдена. Автозапуск после скачивания — нет |
| Тесты | Юнит на парсинг `[mm:ss]`, прореживание, сборку HTML (без сети). Существующие `test_subtitle_merge.py` не ломать |

## Файлы

Новый: [`YouTube_Translator/timecode_player.py`](../../YouTube_Translator/timecode_player.py)

- `parse_timed_lines(text) -> list[{seconds, label}]`
- `thin_marks(marks, min_gap=25) -> list`
- `parse_highlights(folder) -> list`
- `video_id_from_folder_name(name) -> str | None`
- `build_player_html(video_id, marks, highlights) -> str` (экранировать `<>&'"` в подписях)
- `write_player_html(folder, video_id) -> path`

Шаблон HTML внутри этой же функции/константы — проще для GitHub, чем отдельный `.html.j2`.

В [`Subtitle_App.py`](../../YouTube_Translator/Subtitle_App.py):

- после `write_output_texts(...)` вызвать `write_player_html(folder_path, video_id)`
- в `_on_download_done` статус: `+ player.html`
- кнопка «Плеер» → `find_output_folder` + `os.startfile(player.html)`

В [`README.md`](../../YouTube_Translator/README.md): таблица файлов + note про `file://` vs `http.server`.

Тесты: `test_timecode_player.py` (рядом с `test_subtitle_merge.py`).

Не трогать: `Subtitle_App_qt_backup.py`, формат `0_`/`1_` txt, yt-dlp.

## HTML/JS (минимум)

```
[iframe YouTube]     [Полезные]  (если есть)
                     [кнопки прореженных фраз]
```

- `https://www.youtube.com/iframe_api` + `YT.Player`
- `playerVars: { rel: 0 }`
- клик: `player.seekTo(sec, true); player.playVideo()`
- кнопки `data-t="123"` (секунды int)

## Порядок работ

1. `timecode_player.py` + тесты на фикстуре из нескольких `[mm:ss]` строк.
2. Вшить запись в `write_output_texts` / конец шага 3 `download_and_split`.
3. Кнопка GUI + строка статуса.
4. README. Ручная проверка: прогон ссылки → открыть html → клик прыгает.

## Готово когда

Прогнал ссылку → в папке ролика есть `player.html` → открыл → жму метку → плеер прыгает **в том же окне**.

## Не в scope

Скачивание видео, VS Code, облако, сотни кнопок без прореживания, автобраузер после скачивания, перенос папок в `dist/`.
