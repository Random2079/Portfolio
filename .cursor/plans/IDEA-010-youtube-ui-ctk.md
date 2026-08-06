# IDEA-010 — Красивый UI YouTube Translator (CustomTkinter)

## Цель

Окно `Subtitle_App` выглядит нормально (как демо в песочнице), **логика yt-dlp не ломается**.

## Статус: готово (2026-07-27 … 2026-08-06)

## Решение

- Песочницу смотрели: CustomTkinter / PyQt+QSS / Flet.
- **Выбрано: CustomTkinter.**

## Сделано

- Боевой GUI на CTk; логика yt-dlp в фоне; буфер.
- Оптимизация: один JSON (title + дорожки) + один download.
- Ctrl+V на русской раскладке; README/requirements; exe.
- Бэкап PyQt: `Subtitle_App_qt_backup.py`.
- Демо-референс: [`sandbox_ui/demo_customtkinter.py`](../../sandbox_ui/demo_customtkinter.py).
