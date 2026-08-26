# 09 · Авто-watch + телефон

| | |
|---|---|
| **Код** | CLI `watch` в [`cli.py`](../../portfolio_news/cli.py) / [`poller.py`](../../portfolio_news/poller.py); автозапуск и push — нет |
| **Слой** | G–H |
| **Статус** | ⬜ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Сейчас

- `python -m portfolio_news watch` — руками из терминала.
- Toast только Windows.

## Цель

- G: Task Scheduler / автостарт с Windows или демон рядом с `serve`.
- H: канал на iPhone (ntfy и т.п.) — **не** MAX/VK/Telegram, пока пользователь не выберет иначе.

## Не делаем

- VPS «чтобы пушило с облака».
- Боты мессенджеров вслепую.
