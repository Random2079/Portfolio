# 10 · Свой БКС — история / графики / разбор

| | |
|---|---|
| **Код** | [`bcs_client.py`](../../portfolio_news/bcs_client.py) · [`day_attribution.py`](../../portfolio_news/day_attribution.py) · [`position_card.py`](../../portfolio_news/position_card.py) · [`api.py`](../../portfolio_news/api.py) · [`static/dashboard-demo.html`](../../portfolio_news/static/dashboard-demo.html) · *(новые модули по мере K)* |
| **Слой** | K0–K9 |
| **Статус** | K0–K8 · KA–KB ✅; дальше K9… |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

## Шаги

| Шаг | Что | Проверка |
|-----|-----|----------|
| K0 | `.env` + UI список = holdings (БКС-only; главная `/`) | ✅ 2026-09-11 |
| K1 | API операций/сделок → таблица | ✅ `/api/operations` + таблица; live `trade-api-bff-trade-details` |
| K2 | SQLite кэш операций | ✅ `bcs_operations` + upsert |
| KA | День: стоимость + % + топ вкладчиков в Δ | ✅ `/api/day` + KPI «За день» / «Кто двинул день» |
| KB | Смотрю (1) / Остальное; клик дня → разбор | ✅ exclusive focus + day-row click |
| K3 | График цены + маркеры (низкий приоритет) | ✅ `/api/chart/{ticker}` + Chart.js на `/` |
| K4 | Карточка: avg, когда купил, PnL, avg vs текущая | ✅ `/api/position/{ticker}` + блок под графиком; без совет-текстов |
| K5 | Новости/MOEX scope = БКС | ✅ poll/`once`/`/api/news`/`/api/metrics` default = holdings; `--all-tickers` legacy |
| K6 | Daily snapshot → график капитала | ✅ `/api/capital` + блок «Капитал»; недельный backfill с 01.2024 из журнала |
| K7 | Календарь купонов/дивов по своим | ✅ `calendar_own.py` + `/api/calendar` + блок «Что прилетит»; MOEX только фоном, кэш `calendar_cache` |
| K8 | Фильтр операций + CSV | ✅ `ops_history.py`: журнал Snowball (с 2023) + кэш БКС, дедуп по локальной дате; чипы акции/облигации/фонды, период по годам, тикер; `/api/operations.csv` |
| K9 | Toast по новостям портфеля | ✅ + антиспам |

## K9 антиспам (не ломать)

- Не пушить новости **за прошлые дни** при первом/любом опросе.
- Дефолт: **один digest** на poll, не 50 toasts.
- `notify=off` / выключатель в UI обязан глушить сразу.
- Scope = только holdings БКС.

## Запреты

- write / заявки
- «покупай/продавай» в UI или ИИ

## Зависимость

Сначала живой read-токен и разведка эндпоинта истории в доке Trade API.
