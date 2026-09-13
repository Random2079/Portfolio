# Part 01 — MOEX candles

## Код

`app/moex.py`

## Вход / выход

- Вход: тикер (SECID), `days`
- Выход: `(candles, board, error)` где candle = `{ time, open, high, low, close, volume? }`
- `time` = `YYYY-MM-DD` (для Lightweight Charts)

## Поведение

- Дневной интервал ISS (`interval=24`)
- Boards: TQBR → TQTF/TQIF/SMAL → market-level
- Чистый парсер строк ISS — `rows_to_candles` (для тестов без сети)

## Проверка

```bash
python -m pytest tests/test_moex_parse.py -q
```
