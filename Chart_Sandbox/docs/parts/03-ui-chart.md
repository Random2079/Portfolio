# Part 03 — UI chart

## Код

`static/index.html` (HTML + JS, Lightweight Charts CDN)

## Поведение

- Поля: тикер, период (дни), кнопка Load, checkbox Force refresh
- Candlestick series, crosshair, zoom/scroll по времени
- Fetch `/api/candles/{ticker}` → `setData`
- Статус: board / stale / error

## Проверка

Ручной смоук: http://127.0.0.1:8766 → SBER → свечи зумятся.
