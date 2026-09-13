# Part 02 — API + disk cache

## Код

- `app/main.py` — FastAPI, static mount, routes
- `app/cache.py` — read/write `data/cache/{TICKER}_{days}.json`

## Контракт

### `GET /api/candles/{ticker}?days=365&force=0`

```json
{
  "ticker": "SBER",
  "board": "TQBR",
  "days": 365,
  "stale": false,
  "error": "",
  "candles": [{ "time": "2024-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100 }]
}
```

- `force=1` — игнор кэша, тянем MOEX, пишем кэш
- при ошибке сети + есть кэш → `stale: true`, candles из кэша

### Static

`/` → `static/index.html`

## Проверка

```bash
python -m pytest tests/test_api_cache.py -q
python -m uvicorn app.main:app --port 8766
curl "http://127.0.0.1:8766/api/candles/SBER?days=90"
```
