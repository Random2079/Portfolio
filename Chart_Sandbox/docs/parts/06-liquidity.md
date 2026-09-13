# Part 06 — Liquidity / stops (estimate) + backtest hook

## Важно

Это **не** стакан MOEX и не реальные заявки стопов. Оценка по OHLC:
- swing high → зона `stops_above` (liq↑)
- swing low → зона `stops_below` (liq↓)
- equal highs/lows → pooled levels

## Код

- `app/liquidity.py` — чистая логика для бэктеста
- `GET /api/liquidity/{ticker}?days=&force=`
- UI: кнопка **Liq** в `static/index.html` (линии пулов + маркеры свингов)

## Для будущего бэктеста

Стратегия может читать `zones` / `pools` с API или вызывать `build_liquidity_map(candles)` в Python без UI.

## Проверка

```bash
python -m pytest tests/test_liquidity.py -q
curl "http://127.0.0.1:8770/api/liquidity/SBER?days=365"
```
