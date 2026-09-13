# 05 · API + UI

| | |
|---|---|
| **Код** | [`api.py`](../../portfolio_news/api.py) · [`static/dashboard-demo.html`](../../portfolio_news/static/dashboard-demo.html) |
| **Слой** | A–D ✅ · E ⬜ |
| **Статус** | 🟡 (polish UI) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Эндпоинты (канон)

- `GET /api/health`, `/api/tickers`, `/api/news`
- `POST /api/poll` + `GET /api/poll/status`
- `GET /api/metrics`, `/api/dividends`, `/api/coupons`
- `GET /api/holdings`, `/api/holdings/status`
- `GET /api/day` (KA), `GET|PUT /api/focus` (KB)
- `GET /api/chart/{ticker}` (K3), `GET /api/position/{ticker}` (K4)

UI: Snowball-дашборд на `/` (карточки позиций, сделки, лента новостей).  
Poll новостей — через CLI (`once` / `poll`) или `POST /api/poll`.

## Ещё не сделано (слой E)

- Live-обновление ленты во время poll (не только прогресс-бар)
- Купоны human: даты, past/future, шапка %/сумма/валюта
- Vite/React в `frontend/` — заготовка, не блокер

## Проверка

```powershell
python -m portfolio_news serve
# открыть http://127.0.0.1:8765/
```
