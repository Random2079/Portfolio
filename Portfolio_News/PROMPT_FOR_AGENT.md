# PROMPT FOR AGENT — IDEA-003 Новостник портфеля

Скопируй/следуй, когда пользователь сказал «делаем IDEA-003» / фазу дороботок.

## Роль

Фулстек-монитор новостей по тикерам в `Portfolio_News/`. Не инвест-консультант.

## Канон

- `IDEAS.md` → IDEA-003  
- `.cursor/plans/IDEA-003-portfolio-news.md`  
- Не коммитить `.env`, живую БД, секреты  

## Уже сделано — не переписывать с нуля

- Каркас, SQLite, Snowball-тикеры, Google News RU + Smart-Lab  
- UI фильтры kind/сектор  
- **Опрос по scope** (`ticker_id` / `kind` / `category`)  
- **Фоновый poll** + `GET /api/poll/status` + прогресс в UI  
- **Digest-toast** (`notify=digest|off|each`)  
- **MOEX сырой ISS**: `GET /api/metrics` / `dividends` / `coupons` + вкладки. Без PnL.  
- **БКС read-only** (опционально): `BCS_TRADE_REFRESH_TOKEN` → `GET /api/holdings` + вкладка «Позиции БКС». Не trade-api-write.  

## Следующие шаги (когда скажут)

1. UI: live-лента во время poll; купоны human (даты/past-future)  
2. ИИ-чистка шума новостей  
3. Авто-watch / Task Scheduler  
4. Телефон (живой канал)  
5. Investing / эмитенты  
6. Docker — только по просьбе  

## Запреты

MAX/VK/Telegram вслепую; VPS; брокер «купи/продай» / `trade-api-write`; секреты и токены БКС в git.
