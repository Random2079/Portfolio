# WHERE WE ARE
Updated: 2026-09-12 10:45 (local)

## Project / zone
- Repo or folder: `Portfolio_News/` (IDEA-003)
- Active area (one path or feature): day attribution via SQLite + 60s poller

## Goal now
- UI «кто двинул день» быстрый из SQLite; MOEX только фоном раз в минуту (без кнопки).

## Done (this session / recently)
- Day snapshot в SQLite (`day_snapshot`); poller `DAY_POLL_SEC=60` на startup serve
- `/api/day` читает БД; UI soft-poll раз в минуту; бокс не пропадает (spinner/кэш)
- Ранее: K3/K4, группы, Focus UX, privacy по «Портфель»

## Next (one step)
- **K5** (новости/MOEX scope = БКС) или пожить с day-poller и глянуть нагрузку

## Blocked / risks
- Первый тик после рестарта serve всё ещё ждёт MOEX ~несколько сек, пока snapshot пуст
- Публичный ISS: при таймаутах тик пропускается (не копятся параллельные)

## Do NOT
- Не коммитить `.env` / токены; не React `frontend/`; не IDEA-023; не trade-write

## Key files
- `portfolio_news/day_poller.py` — фон раз в минуту
- `portfolio_news/day_cache.py` — SQLite R/W
- `portfolio_news/db.py` — таблица `day_snapshot`
- `portfolio_news/api.py` — `/api/day` + startup poller
- `portfolio_news/static/dashboard-demo.html` — UI

## Open questions
- Оставить 60с или поднять до 120с, если MOEX начнёт тупить
