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
- **MOEX metrics** `GET /api/metrics` + вкладка в UI  

## Следующие шаги (когда скажут)

1. ИИ-чистка шума новостей  
2. Авто-watch / Task Scheduler  
3. Телефон (живой канал)  
4. Investing / эмитенты  
5. Docker — только по просьбе  

## Запреты

MAX/VK/Telegram вслепую; VPS; брокер «купи/продай»; секреты в git.
