# Part 07 — Crypto futures order book (real L2)

## Зачем

Ликва для **фьючей** (не SBER). Публичный Binance USDT-M depth — настоящий стакан лимиток.

## Код

- `app/crypto_book.py` — `fetch_futures_orderbook`
- `GET /api/crypto/orderbook/{symbol}?limit=50`
- UI: `/crypto` → `static/crypto.html` (DOM + live poll 1s)

## Не путать

- Это **bids/asks в книге**, не «где стоят стоп-лоссы клиентов».
- MOEX swing-Liq (`/api/liquidity`) — другая история, для акций.

## Проверка

```bash
curl "http://127.0.0.1:8772/api/crypto/orderbook/BTCUSDT?limit=20"
# браузер: http://127.0.0.1:8772/crypto
```
