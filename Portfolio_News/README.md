# Portfolio News (IDEA-003)

Локальный монитор новостей по тикерам: **FastAPI + SQLite + vanilla UI + Windows toast**. Сырой MOEX + опционально позиции БКС (read-only).

Не инвест-советы. Документация агента: **[docs/](docs/README.md)** (TZ, parts, промпт).

## Структура

```
Portfolio_News/
├── portfolio_news/     ← код (API, poller, MOEX, BCS, static UI)
├── tests/
├── frontend/           ← заготовка Vite (опционально)
├── docs/               ← ТЗ и инструкции → docs/README.md
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
| **KA–KB · K3–K8** | ✅ | День · Focus/Hold · график · карточка · scope БКС · линия капитала · календарь выплат · сделки с 2023 + фильтры/CSV |
| **K9…** | ⬜ | Toast-антиспам по бумагам портфеля… |
| E–J / F | ⬜ | Новостной хвост / разбор без ордеров (позже) |

Полный канон: [docs/TZ.md](docs/TZ.md).
