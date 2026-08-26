# 01 · Core (config / DB / CLI)

| | |
|---|---|
| **Код** | [`config.py`](../../portfolio_news/config.py) · [`db.py`](../../portfolio_news/db.py) · [`cli.py`](../../portfolio_news/cli.py) · [`__main__.py`](../../portfolio_news/__main__.py) |
| **Слой** | A |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Вход / выход

- Settings из `.env` (`HOST`, `PORT`, toast, BCS-токены).
- SQLite `data/news.db`: таблицы `tickers`, `news` (unique URL).
- CLI: `once` / `watch` / `import-tickers` / `serve`.

## Проверка

```powershell
cd Portfolio_News
python -m portfolio_news --help
python -m portfolio_news serve
# http://127.0.0.1:8765/api/health
```
