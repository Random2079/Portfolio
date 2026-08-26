# 04 · Poll + toast

| | |
|---|---|
| **Код** | [`poller.py`](../../portfolio_news/poller.py) · [`poll_job.py`](../../portfolio_news/poll_job.py) · [`notify_toast.py`](../../portfolio_news/notify_toast.py) |
| **Слой** | A–B |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Вход / выход

- Scope: `ticker_id` / `kind` / `category`.
- Фоновый job: прогресс `current/total`, `inserted`.
- `notify=digest|off|each` — digest = один toast на прогон.
- Новая URL → insert + toast; повтор URL → тишина.

## Проверка

```powershell
python -m portfolio_news once --ticker SBER --notify digest
# из UI: «Искать новости» → GET /api/poll/status
```
