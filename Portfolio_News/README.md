# Portfolio News (IDEA-003)

Локальный монитор новостей по тикерам портфеля: **FastAPI + SQLite + UI (vanilla JS) + Windows toast**.

Не инвест-советы. Без Telegram / MAX / VK. Docker — позже.

## Стек

| Слой | Технология |
|------|------------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, SQLite |
| Sources | Google News RU RSS, Smart-Lab news RSS (фильтр по тикеру/имени) |
| Notify | Windows toast (`winotify`) |
| Frontend | Vanilla JS с FastAPI: `http://127.0.0.1:8765/`. Заготовка Vite/React в `frontend/` (нужен Node) |
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

API + UI (один процесс):

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
python -m portfolio_news once --ticker SBER
python -m portfolio_news once --kind equity --category Энергетика
python -m portfolio_news once --notify digest   # один toast
python -m portfolio_news once --quiet           # без toast
python -m portfolio_news watch
```

## API

- `GET /api/health`
- `GET /api/tickers`
- `GET /api/news?ticker=SBER&limit=50`
- `POST /api/poll?ticker_id=SBER&kind=equity&category=...&notify=digest` — старт фона
- `GET /api/poll/status` — прогресс (`current/total`, `ticker_id`, `inserted`)
- `GET /api/metrics?ticker_id=SBER` или `kind`/`category` — сырые котировки MOEX ISS
- `GET /api/dividends?...` — история дивов (`dividends.json`)
- `GET /api/coupons?...` — график купонов (`bondization.json`)
- Без `ticker_id` и при `limit=0` сервер режет до **15** бумаг (анти-долбёжка ISS)

- `GET /api/holdings` — позиции БКС (нужен `BCS_TRADE_REFRESH_TOKEN` в `.env`)
- `GET /api/holdings/status` — настроен ли токен

UI: «Искать новости» шлёт **текущий фильтр/тикер**. Вкладки: Лента / Котировки / Дивы / Купоны / **Позиции БКС**.

### БКС (read-only)

1. Кабинет «БКС Мир инвестиций» → профиль/счёт → токены API → **refresh token** с правом `trade-api-read` (не write).
2. Скопируй `Portfolio_News/.env.example` → `.env`, вставь токен в `BCS_TRADE_REFRESH_TOKEN=...`
3. Перезапусти `python -m portfolio_news serve`, вкладка «Позиции БКС».
4. Токен **не коммитить**. Живёт ~90 дней, потом новый из кабинета.

## Дедуп

В SQLite уникальный `news.url`. Повтор той же ссылки не создаёт строку и не шлёт toast.

## Данные

- БД: `data/news.db` (в `.gitignore`)
- Секреты: `.env` (в `.gitignore`)
- В git: `tickers.example.json` без количеств и PnL

## План / промпт

- `.cursor/plans/IDEA-003-portfolio-news.md` (в корне `DS_Projects`)
- `PROMPT_FOR_AGENT.md`
