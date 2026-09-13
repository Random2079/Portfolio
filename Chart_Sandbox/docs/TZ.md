# Chart_Sandbox — ТЗ (IDEA-024)

## Цель

Локальный свечной график «как TradingView»: Lightweight Charts только рисует, свой API отдаёт дневные OHLC с MOEX ISS + оверлеи.

## Как работать

Фразы: `делаем K0` / `делаем K1` / … — один слой за заход. Git: commit/push только по просьбе.

## MVP / слои

| Слой | Суть | Статус |
|------|------|--------|
| K0 | docs (TZ, parts, PROMPT) | ✅ |
| K1 | FastAPI + static LWC + `GET /api/candles/{ticker}` → живые свечи | ✅ |
| K2 | Диск-кэш `data/cache/`; force; stale при таймауте ISS | ✅ |
| K3 | `GET /api/markers/{ticker}` + маркеры на серии | ✅ |
| K4 | Перемотка (Bar Replay), референс TradingView | ✅ |
| K5 | Ликвидность/стопы (оценка по свингам) + API под бэктест | ✅ |
| K6 | Crypto futures DOM (Binance BTCUSDT L2) | ✅ |

## Не делаем

- iframe TradingView Widget как ядро
- Bybit/крипта вместо MOEX для акций
- Встройка в Portfolio_News (IDEA-003)
- Полный набор TA-индикаторов в MVP
- Советы «купи/продай», торговый бот
- Не обещать «тесты = багов не будет»

## Готово когда

- [x] localhost: тикер → свечи с зумом/скроллом/кроссхейром
- [x] Данные через свой API, не чужой iframe
- [x] Кэш спасает от пустого экрана при таймауте ISS
- [x] Маркеры из JSON видны на графике
- [x] Регрессия на стыках (см. ниже) зелёная
- [x] Replay: скрыты будущие бары; Play/шаг/скорость; Exit → полный ряд

## Регрессия / тесты

### Контракты

1. ISS-строка с `begin` + OHLC → candle `{ time: YYYY-MM-DD, open, high, low, close }`.
2. Строка без OHLC / без `begin` → пропускается.
3. `GET /api/candles/{ticker}` при успешном fetch → `candles` — непустой list словарей с ключами time/open/high/low/close (если MOEX доступен или есть кэш).
4. При ошибке сети и наличии кэша → `stale: true` и непустые `candles`.
5. `GET /api/markers/SBER` → list маркеров из `data/markers.json`.

### Команда прогона

```bash
python -m pytest tests/ -q
```

### Не тестируем автоматом

- Внешний вид / зум «на глаз»
- Живой iss.moex.com в CI (моки / фикстуры строк)

### Ручной смоук

1. `python -m uvicorn app.main:app --port 8766`
2. http://127.0.0.1:8766 → SBER → свечи
3. Force refresh
4. Маркеры buy/sell на SBER

### Политика агента

Меняешь парсер / кэш / API-контракт → гоняй `pytest`. UI — смоук вручную.

## Проверка

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python -m uvicorn app.main:app --reload --port 8766
```

Ожидание: тесты OK; в браузере SBER рисуется (http://127.0.0.1:8766).

## Таблица parts

| Part | Код |
|------|-----|
| [01-moex](parts/01-moex.md) | `app/moex.py` |
| [02-api-cache](parts/02-api-cache.md) | `app/main.py`, `app/cache.py` |
| [03-ui-chart](parts/03-ui-chart.md) | `static/index.html` |
| [04-markers](parts/04-markers.md) | `data/markers.json`, API + UI |
| [05-bar-replay](parts/05-bar-replay.md) | `static/index.html` (replay UI) |
| [06-liquidity](parts/06-liquidity.md) | `app/liquidity.py`, `/api/liquidity`, UI Liq |
| [07-crypto-orderbook](parts/07-crypto-orderbook.md) | `app/crypto_book.py`, `/crypto` |
