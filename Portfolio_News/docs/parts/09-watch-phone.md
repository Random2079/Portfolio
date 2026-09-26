# 09 · Авто-watch + телефон

| | |
|---|---|
| **Код** | CLI `watch`/`once` в [`cli.py`](../../portfolio_news/cli.py) · [`poller.py`](../../portfolio_news/poller.py); Scheduler — ещё нет |
| **Слой** | G–H |
| **Статус** | G ⬜ план в [`MAP.md`](../../MAP.md) **§7G** · H ⬜ |
| **Навигация** | [MAP](../../MAP.md) · [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Канон плана

**Статус / шаги G — только в MAP §7G.** Этот part — техприложение.

## Сейчас

- `python -m portfolio_news once` — один прогон (BCS scope, toast).
- `python -m portfolio_news watch` — цикл вручную в терминале (`POLL_INTERVAL_SEC`, дефолт 900).
- Toast только Windows.

## G (когда «делаем G»)

См. MAP §7G: Task Scheduler → периодический `once`, лог `data/watch_last.json`, опц. строка в UI.  
Не VPS. ИИ в poll — не в G.

## H (позже)

Канал на iPhone (ntfy и т.п.) — **не** MAX/VK/Telegram, пока пользователь не выберет иначе.

## Не делаем

- VPS «чтобы пушило с облака».
- Боты мессенджеров вслепую.
