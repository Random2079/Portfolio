# Документация React Portfolio News

## Открывать отсюда

Backend-документация зеркалится локально в `docs/backend/`, чтобы не прыгать
между sibling-папками:

- [`backend/MAP.md`](backend/MAP.md) — статус, очередь, планы (главный канон)
- [`backend/docs/TZ.md`](backend/docs/TZ.md) — технические слои и регрессия
- [`backend/docs/parts/INDEX.md`](backend/docs/parts/INDEX.md) — parts по подсистемам
- [`backend/docs/PROMPT_FOR_AGENT.md`](backend/docs/PROMPT_FOR_AGENT.md) — вход в новый чат

Зеркало генерируется и не коммитится. Источник правды остаётся в
`../Portfolio_News/`, поэтому документы не расходятся.

Обновить зеркало вручную:

```powershell
npm run docs:sync
```

`npm start` обновляет его автоматически.

## Поток приложения

```text
React /app/
  → Python FastAPI /api/*
    → BCS read-only / MOEX / Google News / SmartLab
    → SQLite-кэши

Ванильный UI /
  → тот же Python API (аварийный бэкап)
```

React не хранит брокерский токен и не обращается в BCS напрямую.

## Один запуск

Из `react_Portfolio_News`:

```powershell
npm start
```

Команда:

1. обновляет локальное зеркало документации;
2. собирает React;
3. запускает sibling `Portfolio_News` (`API + /app/ + ванильный /`).

Если порт `8765` уже занят сервером, сборка и синхронизация выполнятся, а второй
сервер не запустится.
