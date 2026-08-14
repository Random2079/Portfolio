# Portfolio News (IDEA-003)

Локальный монитор новостей по тикерам портфеля: **FastAPI + SQLite + React + Windows toast**.

Не инвест-советы. Без Telegram / MAX / VK. Docker — позже.

## Стек

| Слой | Технология |
|------|------------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, SQLite |
| Sources | Google News RU RSS, Smart-Lab news RSS (фильтр по тикеру/имени) |
| Notify | Windows toast (`winotify`) |
| Frontend | React: сразу на `http://127.0.0.1:8765/` (CDN, без npm). Опционально Vite в `frontend/` если есть Node |
| Тикеры | `tickers.example.json` из Snowball CSV (символы/имена, без PnL) |

## Установка

```powershell
cd Portfolio_News
python -m pip install -r requirements.txt
copy .env.example .env
python -m portfolio_news import-tickers
```

Импорт свежего Snowball из Загрузок:

```powershell
python -m portfolio_news import-tickers "$env:USERPROFILE\Downloads\Snowball Holdings.csv"
```

## Запуск

API + React UI (один процесс):

```powershell
python -m portfolio_news serve
# UI:  http://127.0.0.1:8765/
# API: http://127.0.0.1:8765/api/health
```

Опционально Vite (нужен Node/npm):

```powershell
cd frontend
npm install
npm run dev
# http://127.0.0.1:5173  (прокси /api → :8765)
```

Поллер без UI:

```powershell
python -m portfolio_news once              # один проход + toast
python -m portfolio_news once --limit 5    # первые 5 тикеров
python -m portfolio_news watch             # цикл (POLL_INTERVAL_SEC)
python -m portfolio_news once --quiet      # без toast
```

Ручной опрос из UI: кнопка «Опросить сейчас» → `POST /api/poll`.

## API

- `GET /api/health`
- `GET /api/tickers`
- `GET /api/news?ticker=SBER&limit=50`
- `POST /api/poll?notify=true`

## Дедуп

В SQLite уникальный `news.url`. Повтор той же ссылки не создаёт строку и не шлёт toast.

## Данные

- БД: `data/news.db` (в `.gitignore`)
- Секреты: `.env` (в `.gitignore`)
- В git: `tickers.example.json` без количеств и PnL

## План / промпт

- `.cursor/plans/IDEA-003-portfolio-news.md` (в корне `DS_Projects`)
- `PROMPT_FOR_AGENT.md`
