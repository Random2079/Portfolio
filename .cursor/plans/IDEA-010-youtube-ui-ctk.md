# IDEA-010 — Красивый UI YouTube Translator (CustomTkinter)

## Цель

Окно `Subtitle_App` выглядит нормально (как демо в песочнице), **логика yt-dlp не ломается**.

## Решение (уже сделано)

- Песочницу смотрели: CustomTkinter / PyQt+QSS / Flet.
- **Выбрано: CustomTkinter** — дальше не сравнивать стеки, только перенос в боевой апп.

## Не в scope

- React / Flet  
- Новые фичи скачивания  
- IDEA-011 (таймкоды) — отдельно  
- Повторный выбор UI-фреймворка

## Уже есть

- Демо: [`sandbox_ui/demo_customtkinter.py`](../../sandbox_ui/demo_customtkinter.py)  
- Боевой GUI: [`YouTube_Translator/Subtitle_App.py`](../../YouTube_Translator/Subtitle_App.py) (ещё **PyQt5** — миграция не начата)

## Шаги (осталось)

1. Вынести из `Subtitle_App.py` чистые функции (валидация URL, yt-dlp, папки) — без привязки к PyQt.  
2. Собрать новое окно на CustomTkinter по образцу демо (поле, Скачать, статус, язык RU/EN если есть).  
3. Подключить те же вызовы yt-dlp / поток или `subprocess`, чтобы UI не клинил.  
4. Прогнать: ссылка → субтитры как раньше.  
5. Обновить README YouTube_Translator: запуск + `pip install customtkinter`.  
6. Старый PyQt-UI убрать или оставить `Subtitle_App_qt_backup.py` на одну итерацию.

## Файлы

- `YouTube_Translator/Subtitle_App.py` (или новый `Subtitle_App_ctk.py` → потом заменить)  
- `YouTube_Translator/requirements.txt` (создать, если нет)  
- `sandbox_ui/` — только референс

## Готово когда

Тот же сценарий скачивания работает из CTk-окна; внешне ближе к демо песочницы.
