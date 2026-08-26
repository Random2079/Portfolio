# 05 · API + UI

| | |
|---|---|
| **Код** | [`api.py`](../../portfolio_news/api.py) · [`static/index.html`](../../portfolio_news/static/index.html) |
| **Слой** | A–D ✅ · E ⬜ |
| **Статус** | 🟡 (polish UI) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Эндпоинты (канон)

- `GET /api/health`, `/api/tickers`, `/api/news`
- `POST /api/poll` + `GET /api/poll/status`
- `GET /api/metrics`, `/api/dividends`, `/api/coupons`
- `GET /api/holdings`, `/api/holdings/status`

UI вкладки: Лента / Котировки / Дивы / Купоны / Позиции БКС.  
«Искать новости» шлёт **текущий** фильтр/тикер.

## Ещё не сделано (слой E)

- Live-обновление ленты во время poll (не только прогресс-бар)
- Купоны human: даты, past/future, шапка %/сумма/валюта
- Vite/React в `frontend/` — заготовка, не блокер

## Проверка

```powershell
python -m portfolio_news serve
# открыть http://127.0.0.1:8765/
```
