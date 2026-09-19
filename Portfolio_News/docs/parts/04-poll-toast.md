# 04 · Poll + toast

| | |
|---|---|
| **Код** | [`poller.py`](../../portfolio_news/poller.py) · [`poll_job.py`](../../portfolio_news/poll_job.py) · [`notify_toast.py`](../../portfolio_news/notify_toast.py) |
| **Слой** | A–B · K9 |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Вход / выход

- Scope: `ticker_id` / `kind` / `category` / BCS holdings (K5 default).
- Фоновый job: прогресс `current/total`, `inserted`.
- `notify=digest|off|each` — digest = один toast на прогон; дефолт из `NOTIFY_DEFAULT`.
- Новая URL → insert; повтор URL → тишина.
- **K9:** toast только если `published_at` ≥ сегодня 00:00 Asia/Yekaterinburg; без даты — в БД да, toast нет. UI: вкладка Новости → Toast + «Искать новости».

## Проверка

```powershell
python -m portfolio_news once --notify off
python -m portfolio_news once --notify digest
# UI: Новости → режим toast → «Искать новости» → GET /api/poll/status
```
