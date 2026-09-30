# Portfolio News · React (`react_Portfolio_News`)

Живой React UI утреннего терминала. **API и ванильный бэкап** — в соседней
папке `Portfolio_News/`.

Документация:

- локальный вход: [`docs/README.md`](docs/README.md)
- канон: [`../Portfolio_News/MAP.md`](../Portfolio_News/MAP.md)
- локальное зеркало канона: `docs/backend/` после `npm start` / `npm run docs:sync`

## Утро — одна команда

Из этой папки:

```powershell
npm start
```

Она синхронизирует документацию, собирает React и запускает Python API+UI.
Остановить сервер: `Ctrl+C`.

- **React:** http://127.0.0.1:8765/app/  
- **Ваниль (бэкап):** http://127.0.0.1:8765/  

`/api` — тот же сервер (same-origin). Vite для утра не нужен.

## Разработка UI (два процесса)

```powershell
# терминал 1
cd ..\Portfolio_News
python -m portfolio_news serve

# терминал 2
cd ..\react_Portfolio_News
npm run dev
```

Открыть: http://127.0.0.1:5173/  
Vite проксирует `/api` → `:8765`. `api.js` по умолчанию ходит относительными путями.

Переопределить API: `VITE_API_BASE=http://127.0.0.1:8765` в `.env`.

## Слои

| Слой | Что |
|------|-----|
| **R0** | Шелл, тема, motion, health + day KPI |
| **R1** | День топ + позиции / focus (`/api/holdings`, `/api/focus`) |
| **R2** | Разбор: график + карточка + KS |
| **R3** | Новости + F-A |
| **R4** | Сделки + календарь |

Текущий статус и очередь не дублируются здесь — см. MAP.
