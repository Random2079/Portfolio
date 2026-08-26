# 02 · Тикеры (Snowball → SQLite)

| | |
|---|---|
| **Код** | [`import_tickers.py`](../../portfolio_news/import_tickers.py) · [`tickers.example.json`](../../tickers.example.json) |
| **Слой** | A |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Вход / выход

- Вход: `tickers.example.json` или Snowball CSV (символ, имя, kind, category).
- Выход: строки в `tickers`. **Без qty/PnL в git.**

## Проверка

```powershell
python -m portfolio_news import-tickers
# или: python -m portfolio_news import-tickers "$env:USERPROFILE\Downloads\Snowball Holdings.csv"
```
