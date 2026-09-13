# Chart_Sandbox (IDEA-024)

Локальный свечной график «как TradingView»: **Lightweight Charts** рисует, **свой API** отдаёт OHLC с MOEX ISS.

## Дерево

```
Chart_Sandbox/
├── app/           # FastAPI, moex, cache
├── static/        # UI + Lightweight Charts
├── data/          # markers.json, cache/
├── docs/          # TZ, parts, PROMPT
├── tests/
└── requirements.txt
```

## Запуск

```bash
cd Chart_Sandbox
pip install -r requirements.txt
python -m pytest tests/ -q
python -m uvicorn app.main:app --reload --port 8766
```

Открой http://127.0.0.1:8766 → тикер `SBER`.

Crypto DOM (фьючи): http://127.0.0.1:8766/crypto — стакан Binance `BTCUSDT`.

## API

- `GET /api/candles/{ticker}?days=365&force=0`
- `GET /api/markers/{ticker}`

Агент: [`docs/TZ.md`](docs/TZ.md).
