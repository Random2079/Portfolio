# 06 · MOEX ISS (сырой dump)

| | |
|---|---|
| **Код** | [`metrics_moex.py`](../../portfolio_news/metrics_moex.py) · [`tests/test_metrics_moex.py`](../../tests/test_metrics_moex.py) |
| **Слой** | C |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Вход / выход

- SECID cache, `effective_moex_limit` (без `ticker_id` → cap 15).
- Котировки / dividends.json / bondization.json → строки для API.
- **Не** PnL, не «анализ портфеля».

## Проверка

```powershell
pytest tests/test_metrics_moex.py -q
# вручную: GET /api/metrics?ticker_id=SBER
```
