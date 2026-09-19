# Portfolio News (IDEA-003)

Локальный монитор новостей по тикерам: **FastAPI + SQLite + vanilla UI + Windows toast**. Сырой MOEX + опционально позиции БКС (read-only).

Не инвест-советы. **Карта:** [MAP.md](MAP.md). Техника агента: **[docs/](docs/README.md)**.

## Структура

```
Portfolio_News/
├── MAP.md              ← статус / очередь / план F-A
├── portfolio_news/     ← код (API, poller, MOEX, BCS, static UI)
├── tests/
├── frontend/           ← заготовка Vite (опционально)
├── docs/               ← TZ + parts → docs/README.md
├── tickers.example.json
├── .env.example
└── requirements.txt
```

## Быстрый старт

```powershell
cd Portfolio_News
python -m pip install -r requirements.txt
copy .env.example .env
python -m portfolio_news import-tickers
python -m portfolio_news serve
# UI:  http://127.0.0.1:8765/
# API: http://127.0.0.1:8765/api/health
```

БКС (опционально): в `.env` → `BCS_TRADE_REFRESH_TOKEN=…` (не коммитить). Подробности — [docs/parts/07-bcs.md](docs/parts/07-bcs.md).

CLI без UI: `python -m portfolio_news once --ticker SBER --notify digest` · `watch`.

## Слои (кратко)

| Слой | Статус | Что |
|------|--------|-----|
| A–D | ✅ | Новости, poll/scope, MOEX, БКС позиции (каркас) |
| **K0–K2** | ✅ | Список БКС + история сделок + кэш |
| **KA–KB · K3–K9** | ✅ | День · Focus · график · карточка · scope БКС · капитал · календарь · сделки + CSV · toast-антиспам |
| E / F / G–H / J / KV | ⬜ | Хвост: polish / ИИ / watch / телефон / Docker / визуал — очередь в MAP |

Полный канон статуса/очереди: [MAP.md](MAP.md). Техника: [docs/TZ.md](docs/TZ.md).
