# Portfolio News · React (`react_Portfolio_News`)

Новый UI-трек (R0+). **API и ванильный бэкап** — в соседней папке `Portfolio_News/`.

Карта: [`../Portfolio_News/MAP.md`](../Portfolio_News/MAP.md) §7R.

## Утро (один процесс)

Сначала один раз собрать UI (после правок React — снова):

```powershell
cd ..\react_Portfolio_News
npm run build
```

или из `Portfolio_News`: `.\scripts\build_react_ui.ps1`

Потом только API:

```powershell
cd ..\Portfolio_News
python -m portfolio_news serve
```

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
| R2… | см. MAP §7R |
