# MAP — Portfolio_News (IDEA-003)

**Это главная карта для тебя.** Один файл: что есть, что дальше, как устроено, что нельзя.  
Обновлено: **2026-10-03**.

Остальные `docs/TZ.md`, `docs/parts/*`, `.cursor/WHERE_WE_ARE.md`, `.cursor/plans/*` — техника или **указатели сюда**.  
Статус / очередь / план следующего слоя **не дублировать** в parts и plans.  
**Расхождение → править этот MAP**, потом при желании подчистить хвосты.

---

## 1. Что это за прога

Локальный **утренний терминал** своего портфеля БКС (read-only):

- позиции, день, сделки, календарь, новости+toast  
- разбор бумаги: карточка + график + **сверка/факты**  
- не советник, не торговый бот, не «купи/продай»

**Запуск утро:** `python -m portfolio_news serve` →  
- React: http://127.0.0.1:8765/app/ (нужен `npm run build` в `react_Portfolio_News`)  
- Ваниль-бэкап: http://127.0.0.1:8765/  
**Одна команда из React-папки:** `.\start.cmd` → sync docs + build + тот же `serve` (`npm.cmd`, без блокировки `npm.ps1`).  
После правок API — **перезапустить serve**. После правок React — `npm run build`, потом refresh (перезапуск serve только если dist не было).

**Репо:** `Portfolio_News/` · React UI: sibling `react_Portfolio_News/` · IDEA-003

---

## 2. Где мы сейчас (одним абзацем)

**Терминал жить (ваниль):** K0–K9 + KA/KB + KS + F-A/F-B ✅ — **заморожен как бэкап** на `/`, не пилим фичи/KV сюда.  
**React:** sibling `react_Portfolio_News/` → после `npm run build` отдаётся **тем же** `serve` на `/app/` (Vite для утра не нужен).  
Если React «пизда» → снова `/` ванили.  
**Очередь:** React MVP R0–R4 ✅. Источники: Google/SmartLab/Pulse/TG ✅. **bond→issuer** ✅ (poller query по эмитенту). **e-disclosure** — проверен браузером (Сбер id=3043), источник в код ещё не врезан. Дальше: e-disclosure source · UI лента coverage · §7F / G / Privacy по желанию. TG новые каналы — стоп.

---

## 3. Два трека (не два параллельных плана)

| Трек | Суть | Статус |
|------|------|--------|
| **Ваниль / бэкап** | K0…K9, KA/KB, KS, F — `dashboard-demo.html` | ✅ **freeze** — только багфиксы API по нужде |
| **React UI** | `react_Portfolio_News/` Vite+React, референс = ванильный дашборд | ✅ **R0–R4** (MVP) · дальше хвосты/G |
| **Хвосты ванили** | G watch, H телефон, чат в старом UI… | следующий ориентир: **G** (§7G) |

Не делаем «два UI-плана сразу» внутри React: один слой за раз (сначала шелл+день+позиции → график/сверка → новости…).

---

## 4. Слои — вся таблица

### Каркас новостей (давно)

| Слой | Статус | Что |
|------|--------|-----|
| A | ✅ | FastAPI, SQLite, тикеры, RSS, CLI, toast, UI |
| B | ✅ | Poll по scope, digest-toast |
| C | ✅ | MOEX сырой |
| D | ✅ | BCS позиции |

### Новостной хвост

| Слой | Статус | Что |
|------|--------|-----|
| E | ⬜ | Polish ленты — низкий приоритет |
| **F** | ✅ | **A** чистка ленты + **B** разбор тикера → чат позже |
| G | ⬜ | Авто-watch — **план §7G** |
| H | ⬜ | Телефон (ntfy…) |
| J | ⬜ | Docker — только по просьбе |
| KV | ⏸ | Визуал ванили → трек React (`react_Portfolio_News`, §7R) |
| **R0…** | ✅ R0–R4 MVP | React UI в `react_Portfolio_News/` |

### Терминал БКС

| Слой | Статус | Что |
|------|--------|-----|
| K0 | ✅ | Только BCS, главная = dashboard |
| K1–K2 | ✅ | История сделок + кэш SQLite |
| KA | ✅ | День: стоимость, Δ, «кто двинул» |
| KB | ✅ | Focus / клик → разбор (API остался) |
| K3 | ✅ | График цены + маркеры сделок (LWC) |
| K4 | ✅ | Карточка: avg, PnL, доля |
| K5 | ✅ | Новости/MOEX = только свои бумаги |
| K6 | ✅ | Капитал / недели × MOEX |
| K7 | ✅ | Календарь купонов/дивов по своим |
| K8 | ✅ | Сделки с 2023 + фильтры + CSV |
| K9 | ✅ | Toast только по своим + антиспам |
| **KS** | ✅ | Сверка под карточкой |

Отложено отдельно: **IDEA-023** forecast, **IDEA-024** chart sandbox — не трогать без команды.

---

## 5. Сверка (KS) — источники и дырки

| Источник | Даёт |
|----------|------|
| BCS | qty, доля, имя |
| MOEX | цена, див/купон, YTM… |
| calendar | ближ. выплаты по своим |
| SmartLab | P/E P/B ROE FCF CAPEX, выручка YoY, контракты девелопа |
| Dohod | оферта/рейтинг облиг |
| ЦБ ПИФ xlsx | TER-прокси: УК% · макс.% (кэш ~7д) |

| Слот | Как закрыли / статус |
|------|----------------------|
| Эскроу девелоп | контракты SmartLab + долг (не cash на эскроу) |
| Growth IT | выручка YoY `field=revenue` |
| TER фонд | ЦБ по ISIN |
| Кэш на добор | вручную, не API |
| Красные флаги | ручной клик, без авто-балла |

---

## 6. Очередь «что делать» (сверху вниз)

1. ~~**R0**~~ ✅ шелл + прокси + day KPI (`react_Portfolio_News`)  
2. ~~**R1**~~ ✅ день топ + позиции / focus  
3. ~~**R2**~~ ✅ разбор: карточка + график LWC + сверка KS  
4. ~~**R3**~~ ✅ новости (+ ИИ-бейджи F-A)  
5. ~~**R4**~~ ✅ сделки / календарь  

**React MVP закрыт.** Дальше по желанию (не автостарт):

1. ~~**§7N**~~ ✅ лента: срочно / факты / сырое; карточка → День+разбор  
2. ~~**pre-AI noise**~~ ✅ denylist паттернов («идея в Профите» / тех.анализ / фьючерсы) + near-dup + short-ticker + **geo/macro keep** (`news_noise.py`) — до DeepSeek; AI-промпт не шумит RU-гео как «макро без бумаги». Не бан всей площадки BCS Profit / Pulse — см. **§7S**  
3. **§7F F-AI polish** — промпты `ai_noise` / `ai_ticker` (нужны для сортировки срочности); рядом — **DeepSeek usage meter** ✅ (баланс + токены на Новостях, см. §7F)  
4. **Privacy** — **запланировано** (§7P), UI ещё нет  
5. ~~**§7S Pulse allowlist v1**~~ ✅ fetch Interfax + Advokat_Manasyan via SSR mirror (`pulse_allowlist.py` + json); source tag `pulse_allowlist`; Investokrat out.  
5b. ~~**§7S Pulse news-by-ticker**~~ ✅ equity only: `/invest/stocks/{TICKER}/news/` → `investSocialNewsByTicker` (`pulse_news_ticker.py`, tag `pulse_news_ticker`); drop-list nicknames + target-title soft filter; bonds/funds позже. **UI allowlist** / maybe/IR pack — не этот слой  
6. **G** авто-watch (§7G) / H телефон  

**Сделки:** тип = радио (Все / акции / облиг / фонды) + подфильтры только у одного вида ✅.  

---

## 7. План F-A — ✅ сделано (справка)

**Зачем:** на вкладке «Новости» видеть шум vs ок, без ордеров.

**Триггер:** кнопка **«Прогнать ИИ»** по сегодняшним (scope BCS).  
Авто в poller — **не в A** (и не добавлено).

**Модель:** DeepSeek JSON-only (`portfolio_news/ai_noise.py`).  
Ключ: `DEEPSEEK_API_KEY` + `AI_NOISE_ENABLED=true` в `Portfolio_News/.env`.

### Ответ модели

| Поле | Значения |
|------|----------|
| `label` | `noise` \| `relevant` \| `dup` |
| `urgency` | `low` \| `mid` \| `high` (если relevant) |
| `reason` | коротко ≤120 |
| `model` / `as_of` | служебное |

### Что в коде

| Шаг | Статус |
|-----|--------|
| **A0** | ✅ `news_ai_cache` |
| **A1** | ✅ `ai_noise.py` + pytest парсера |
| **A2** | ✅ `POST /api/news/ai-classify`, `GET /api/news/ai-status`, поля в `/api/news` |
| **A3** | ✅ кнопка + бейджи + «скрыть шум» (localStorage) |
| **A4** | ✅ pytest; смоук — с ключом в .env |

### Не в F-A (по-прежнему)

Авто-classify в poll, разбор тикера (B), чат, forecast 023, замена RSS на LLM.

### F-B — ✅ сделано (справка)

**Зачем:** по выбранному тикеру — one-shot «на что бьют новости» + чеклист к стратегии. Не чат, не ордер.

**Триггер:** кнопка **«Разбор ИИ»** в блоке под сверкой KS (разбор бумаги).  
Кэш SQLite `ticker_ai_review_cache` ~6ч; «Ещё раз» = force.

**API:** `POST /api/ai/ticker-review`, `GET /api/ai/ticker-review/{ticker}`  
**Код:** `portfolio_news/ai_ticker.py` · тот же `DEEPSEEK_API_KEY` + `AI_NOISE_ENABLED`.

### Чат (кратко, потом)

- Быстрые вопросы по данным приложения; не замена B.

---

## 7F. F-AI polish — очередь (ещё не кодим)

**Статус:** F-A/F-B = кнопки + API ✅; **качество ИИ-слоя сырое**. Терминалом пользоваться можно.  
**Pre-AI (дешёво, без токенов):** ✅ denylist **паттернов** («идея в Профите», «Технический анализ», фьючерсный спам, `#сильный_рост`) + near-dup fingerprint (poller drop + GET `/api/news` + auto-`dup` в classify) + short-ticker guard (len≤2 → нужны name-токены) + **geo/macro keep** (война/санкции/… не junk; hard spam-паттерны всё равно drop) в SmartLab/Google.  
Это **не** «забанить BCS Profit / весь Pulse»: спам-продукт и авторы с реальных новостей — разные вещи (**§7S**).  
**Не трогать без нужды:** дальше regex в `news_noise.py` только если новый явный junk-паттерн.

### `ai_noise.py` — чего не хватает

| # | Что |
|---|-----|
| 1 | ✅ `kind` (stock/bond/fund) в промпт |
| 2 | ✅ имя эмитента |
| 3 | ✅ 1 строка роли (category / bond / fund / equity) |
| 4 | 3–4 few-shot (`noise` / `relevant` / `dup`) |
| 5 | явный `dup` (тот же event / смысл за 48ч) |
| 6 | ✅ не ставить `high` только из кликбейта «срочно» — post-model guard demote `high→mid`, если в заголовке нет жёсткого события |
| позже | snippet 1–2 предложения (title-only врёт) |

### `ai_ticker.py` — чего не хватает

| # | Что |
|---|-----|
| 1 | факт позиции (qty / есть ли / ядро\|хвост) |
| 2 | отсылка к чек-поинту одной строкой |
| 3 | ветка `kind=bond` (оферта / купон / рейтинг / ковенанты) |
| 4 | калибровка `urgency` |
| 5 | KS labels = подсказки, не факты |

### Порядок допила (когда «делаем F-AI»)

1. ✅ `kind` + name + bucket (роль) в `ai_noise` + строгий `high` guard  
2. few-shot / dup calibration  
3. holding + bond/equity-ветка в `ai_ticker`  

### DeepSeek usage meter — ✅ (2026-10-02)

Счётчик расхода API рядом с polish, не часть промптов §7F.

- **Лог:** `ai_usage.py` — после каждого `_call_deepseek` (classify / ticker-review) строка в `data/ai_usage.jsonl` (tokens + оценка `$` по прайсу в константах).  
- **Баланс:** DeepSeek `GET /user/balance`, кэш 5 мин; после «Прогнать ИИ» — свежий.  
- **API:** поля в `GET /api/news/ai-status` (`balance`, `today_*`, `month_*`).  
- **UI:** строка рядом с «Прогнать ИИ» на **Новостях**; месяц — в tooltip.  
- **Позже (по желанию):** дневной `$` cap — стоп AI-кнопок при превышении.  

---

## 7N. Новости UI — канон ✅ (React `/app/`)

**Зачем утром:** кто / что вышло / надо ли разбирать сейчас. Не каша из 50 ссылок Google.  
**Код:** `react_Portfolio_News/src/NewsFeed.jsx` (+ CSS). Отдельного `docs/parts/` нет — канон здесь.

### Макет (зафиксировано 2026-09-30)

| Блок | Что |
|------|-----|
| **Срочно / к разбору** | Новости, что бьют в фундамент; **карточки по бумагам** (не плоский список новостей). Под карточкой 1–3 заголовка. Сортировка бумаг и заголовков по важности (F-A: `relevant` + `urgency`) |
| **Факты / среднее** | Спокойный этаж, тоже карточки + сортировка |
| **Шум** | **Не показывать** (не свёртка) |
| **Без ИИ** | Блок «Срочно» пустой / призыв «Прогнать ИИ»; всё сырое не мимикрирует под срочное |

### Строка / карточка

- **Кто:** тикер + лого (как на Дне, `/static/logos`)  
- **Что:** заголовок новости (+ дата, когда допилим)  
- **Срочно ли:** метка из F-A (`high` / `mid` / `low`)  
- **Клик по бумаге / «в разбор»:** уход на вкладку **День**, открыть **разбор этой бумаги** (график + KS + F-B ИИ-разбор + источник/ссылка на новость там же или рядом). Разбор = одна страница Дня, не отдельный чат

### Связки

- Сортировка срочности → F-A (+ позже **§7F**, иначе `high` из кликбейта врёт)  
- «На что влияет» подробно → F-B в разборе, не простыня в каждой строке ленты  
- Автоподтягивание ленты без кнопки → **§7G**, не этот слой  

### Порядок кода (когда «делаем 7N») — ✅

1. ✅ Навигация Новости → День + selected ticker (+ якорь разбора)  
2. ✅ Лого + дата в карточке  
3. ✅ Два этажа + скрытие noise (после F-A); сырое отдельно, не под срочное  
4. ✅ Группировка по тикеру, сортировка по urgency  

---

## 7S. Источники — allowlist каналов (не бан площадки)

**Подход:** не выкидывать целиком Pulse / BCS Profit / Telegram / Яндекс. Whitelist **каналов/авторов**, которые пишут факты (отчётность, M&A, эмиссии, макро, IR эмитента). Hard denylist в `news_noise.py` на фразы вроде «идея в Профите» — **оставить** (это спам-продукт, не «все авторы BCS»).

**Pulse mirror (research 2026-10-01):**  
`https://www.tbank-online.com/invest/pulse/` — зеркало Tramvai (`x-tramvai-resolved-external-host` → tinkoff.ru), **HTTP 200**, SSR HTML ~1.3–2 MB с постами и никнеймами; `x-robots-tag: noindex`. Профили: `/invest/social/profile/{nickname}/` (иногда + UUID). Полки «каналы/медиа» на главной (T-Journal, RBC_Investments, Interfax, ProCFA, tj_invest, IR эмитентов…). Тикеры в постах как `$SBER` / `{$GAZP}`.  
**По тикеру (HTML):**  
- `/invest/stocks/{TICKER}/pulse/` — SSR 200, но **посты пустые** (`pulsePostsInit.state={}`); соцлента только через social-api (без сессии → «Сервис временно недоступен»). **Не** источник v1.  
- `/invest/stocks/{TICKER}/news/` — SSR 200 + child-app JSON **`investSocialNewsByTicker[TICKER].items`** (новости T-Investments / Interfax / …) — **это** путь для покрытия своих акций (**§7S 5b** ✅).  
Child-apps на CDN: `pulse-news-by-ticker`, `pulse-posts-by-ticker`, …

**Как тянуть данные:**  
- **HTML scrape** профиля `/invest/social/profile/{nickname}/` — SSR `__TRAMVAI_STATE__` (allowlist v1).  
- **HTML scrape** `/invest/stocks/{TICKER}/news/` — `investSocialNewsByTicker` (news-by-ticker, equity).  
- **XHR:** social-api-gateway — без сессии Error; **не** используем.  
- **ToS / хрупкость:** зеркало `noindex`, неофициально; смена child-app / ключа `pulseGetProfilePage` / `investSocialNewsByTicker` ломает парсер.

### Confirm 2026-10-01 (Investing chat triage) ✅

Политика зафиксирована. Config: `portfolio_news/sources/pulse_allowlist.json`.

| Вердикт | Ники / правило |
|---------|----------------|
| **v1 (hard allowlist)** | `Interfax` (wire) · `Advokat_Manasyan` (legal/bond facts) |
| **maybe (не v1)** | `Investokrat` — **locked OUT of v1** (confirm 2026-10-01 user): opinion-frame / soft ideas поверх фактов; остаётся в maybe на later · `T-Investments` — post-filter: drop/downgrade «аналитики / целевая / повысили оценку»; keep issuer news / divs / placement · `Karsotel` — develop overlap · `slavik_capital` — banks, opinion-heavy (**maybe↓**) |
| **drop** | `Tamonkin_Dmitriy`, `T-Journal`, `ProCFA`, `CyberWish`, `SamNakopil`, `Pulse_Official` / `Pulse_Authors`, мёртвые `RBC_Investments` / `tj_invest` / `brandhamster`, `TraderOrInvestor` |
| **IR pack** | **не в v1**; только **v1.1** и только если тикер в live BCS holdings |

### Pulse allowlist v1 — код ✅ (2026-10-01)

- **Модуль:** `portfolio_news/sources/pulse_allowlist.py` · source tag `pulse_allowlist` · в `default_sources()` рядом с Google/SmartLab.
- **Fetch:** `{mirror_base}/invest/social/profile/{nickname}/` → парсим `__TRAMVAI_STATE__` → `seoSsrData.pulseGetProfilePage.feed.data.items` (не XHR social-api).
- **Нормализация:** title (article) / первая строка body (simple) → `RawNews`; URL профиля+post id; `publishedAt` ISO.
- **Фильтры:** chip-stripped prose (`title_matches_ticker` / issuer name; игнор `$TICKER` и `/invest/stocks/…` deep-links) **или** ≤2 instrument tags; `is_noise_title`; near-dup — в `poller._insert_if_new`. Кэш постов на инстанс источника (один раз за poll). Investokrat / maybe — не fetch.
- **Failure mode (хрупкий SSR):** нет usable JSON / нет `pulseGetProfilePage…items` / HTTP fail → warning в лог, пустой список (Google/SmartLab не трогаем). Зеркало `tbank-online.com` неофициальное (`noindex`); смена Tramvai-ключа ломает парсер. Interfax часто без instruments → посты без имени эмитента в title не сядут на holdings.

### Pulse news-by-ticker — код ✅ (2026-10-02)

- **Модуль:** `portfolio_news/sources/pulse_news_ticker.py` · source tag `pulse_news_ticker` · в `default_sources()`.
- **Зачем:** allowlist авторов не кроет тонкие позиции (X5 / LSNGP / TRNFP / CHMF…), пока Interfax/Advokat не написали; вкладка новостей бумаги даёт ленту **по тикеру**.
- **Fetch:** `{mirror_base}/invest/stocks/{TICKER}/news/` → child-app JSON → `stores.investSocialNewsByTicker[TICKER].items`.
- **Scope:** только `kind=equity` (не bond/fund; ISIN/`RU000*` skip). Облиги → эмитент — later.
- **Фильтры:** тикер в `content.instruments`; `is_noise_title`; nicknames из `pulse_allowlist.json` **drop**; soft-drop «целевая цена / повысили оценку»; broad digest (>3 instruments без имени/тикера в title) → skip. Кэш HTML-parse на тикер в рамках инстанса poll.
- **Failure mode:** нет `investSocialNewsByTicker` / HTTP fail → [] (остальные источники живы).

**Утренние типы источников (канон):**

| Держать | Не утро / не v1 |
|---------|-----------------|
| wire | таргеты / «повысили оценку» |
| IR / events **своих** бумаг | идеи «купи» / интрадей |
| legal / bond facts | Pulse Official social |
| macro CB / tariffs / taxes — **только** если бьёт в сектор / позицию (как geo-keep) | CFA edu noise · foreign IR |

**Macro/geo:** keep только если сектор / regulatory / тикер из checkpoint / holdings — align с существующим geo-keep в `news_noise.py`.

**Telegram allowlist v1 — код ✅ (2026-10-03):**  
- Публичный preview `https://t.me/s/{slug}` (без userbot).  
- **v1:** [Рубиндей](https://t.me/rubinday50) · [РКИ](https://t.me/information_disclosure) · [Интерфакс.Рынки](https://t.me/ifax_go).  
- **Не брать:** `i_moex` — не офиц. MOEX, «в разработке», в описании TA/идеи, лента смешанная (аудит 2026-10-03).  
- Модуль: `telegram_allowlist.py` + json · tag `telegram_allowlist` · в `default_sources()`.  
- Кэш постов на инстанс poll; матч `title_matches_ticker` по тексту поста; `is_noise_title`. Preview ~20 последних постов / канал.  
- Failure: HTTP/parse fail → [] (остальные источники живы). Закрытые каналы / userbot — не этот слой.

**Вне Pulse (later):** TG **Архивариус**, **Вредные** — daily fact sources; добавить slug в `telegram_allowlist.json`, не userbot.

Критерий как у пользователя + Investing `чек-поинт.md`: факты/макро по секторам KS, не идеи / таргеты / интрадей. Hard denylist «идея в Профите» остаётся; площадка ≠ все авторы.

**Coverage / poll hygiene (2026-10-03):**  
- Активные источники в `default_sources()`: `google_news_ru` · `smartlab` · `pulse_allowlist` (2 канала: Interfax, Advokat_Manasyan) · `pulse_news_ticker` (equity) · `telegram_allowlist` (Рубиндей · РКИ · ifax_go).  
- Аудит CLI: `python -m portfolio_news coverage --window 7d` (BCS scope; `--all-tickers` для offline).  
- Google: минус `#сильный_рост` в RSS-query **ломал ленту (0 entries)** — убран; denylist title остаётся.  
- После фикса — нужен `once`/`watch` poll, чтобы заполнить `pulse_news_ticker` и оживить Google в DB.

**bond→issuer ✅ (2026-10-04):**  
`bond_issuer.py` + `bond_issuer.json` — ISIN → issuer aliases (+ optional `equity_ticker`). Poller передаёт в источники **issuer query**, не «Магнит БО-004Р-08». Heuristic fallback по имени BCS. URL в DB глобально уникален → одна новость не дублируется на акцию+облиг (ок).  
Тесты: `tests/test_bond_issuer.py`.

**e-disclosure (проверка 2026-10-04, код источника ещё нет):**  
- Браузер: после JS-check главная и `company.aspx?id=3043` (Сбер) открываются **без логина/капчи**; `event.aspx` ссылки парсятся из DOM.  
- urllib/requests — timeout/403, нестабильно.  
- Карта id: `sources/e_disclosure_companies.json` (пока SBER=3043, остальное добить).  
- Следующий слой: источник `e_disclosure` (браузерная сессия / Playwright) по `company_id` holdings+issuer → не в `default_sources` пока не стабилен.

**Дальше:** e-disclosure source · UI coverage ленты · maybe/IR · ещё company_id в json · TG стоп.

---

## 7P. Privacy (screen mode) — план, UI ещё нет

**Статус:** 📋 запланировано (не сделано). Не путать с VPN / шифрованием / секретами.

**Зачем:** режим экрана для скриншотов и скринкаста — скрыть деньги, оставить «что происходит».

| Скрыть | Оставить |
|--------|----------|
| day KPI totals, PnL | тикеры, лого |
| рыночная стоимость позиций | заголовки новостей |
| «кто двинул» ₽ / % | формы графиков (оси можно маскировать или оставить как есть) |
| avg / ₽ на карточке | |

**UI (когда «делаем privacy»):** тумблер в header → `localStorage`, **без сервера**.  
**Не трогать:** `.env`, токены, API-секреты, бэкенд auth.

**Не в этом слое:** полный polish §7F, G/H.

---

## 7G. План G — авто-watch (ещё не кодим)

**Зачем:** не сидеть и не жать «Искать новости». Лента и toast сами, пока ПК включён / ты в сессии Windows.

**Уже есть (не G):** `python -m portfolio_news once` и `watch` (цикл + `POLL_INTERVAL_SEC`, дефолт 900). Toast digest/each/off. Scope BCS.  
**Нет:** автозапуск без открытого терминала.

### Решение (зафиксировать)

| | Выбор |
|--|--------|
| **Как гонять** | **Windows Task Scheduler** → периодический `once` (не вечный `watch` в фоне) |
| **Зачем не в `serve`** | serve часто гасишь; Scheduler живёт отдельно; проще отладка |
| **Интервал** | **15–30 мин** (`POLL_INTERVAL_SEC` / ключ задачи). Утро: чаще не нужно |
| **Toast** | как сейчас: `NOTIFY_DEFAULT=digest` (только сегодняшние, BCS) |
| **ИИ** | **не** в G: F-A/F-B по кнопке. Авто-classify в poll — отдельное решение позже |
| **ПК sleep** | пока спит — не опрашивает (ок для домашнего терминала) |

Альтернатива (не в MVP G): фоновый poller внутри `serve` как `day_poller` — только если потом сам попросишь «всё в одном процессе».

### Шаги реализации (когда «делаем G»)

| Шаг | Что |
|-----|-----|
| **G0** | Скрипт/инструкция: создать задачу Scheduler (`scripts/install_watch_task.ps1` или `.bat`) — путь к python + `python -m portfolio_news once --notify digest`, working dir = `Portfolio_News`, интервал 15–30 мин, при входе в Windows + повтор |
| **G1** | Лог последнего прогона: файл `data/watch_last.json` (ts, inserted, error) — чтобы UI/ты видел «когда последний раз опросил» |
| **G2** | Опц. UI: строка на Новостях «авто: последний раз …» + ссылка «как включить» (не обязательно ставить задачу из браузера) |
| **G3** | Смоук: задача в Scheduler → `once` без окна → toast при новых; ПК без serve тоже копит новости в SQLite |

### Не в G

- VPS / облачный cron  
- Telegram/MAX/VK  
- H (телефон / ntfy) — следующий слой  
- Авто F-A после каждого poll  
- Переписывать poller с нуля  

### Готово когда

- [ ] Задача Scheduler ставится одним скриптом / короткой инструкцией в MAP или `docs/`  
- [ ] `once` по расписанию без открытого терминала  
- [ ] Видно время последнего успешного прогона  
- [ ] Toast/лента как при ручном «Искать новости»

---

## 7R. План React UI (референс = ваниль)

**Зачем:** красота, анимация, удобство; пощупать React.  
**Где код:** sibling-папка **`DS_Projects/react_Portfolio_News/`** (не внутри freeze ванили).  
**Бэкап:** `serve` `/` = ваниль `dashboard-demo.html`.  
**Утро:** один процесс — `serve` отдаёт API + собранный React на **`/app/`** (`dist/` после `npm run build`).  
**Пилить UI:** `npm run dev` на `:5173` + тот же API.  
**Старый** `Portfolio_News/frontend/` — черновик, не канон.

### Правила отката

- Ваниль = источник правды по *поведению* и запасной UI.  
- Утро можно открывать на `/` ванили, пока React не закрыл сценарий.  
- «Пизда» → стоп React, пользуемся ванилью; папку `react_Portfolio_News` можно не трогать.

### Слои

| Слой | Статус | Что |
|------|--------|-----|
| **R0** | ✅ | Vite+React шелл, прокси `/api` → 8765, тема+motion, health + day KPI |
| **R1** | ✅ | День топ + список позиций / focus (клик = selection для R2) |
| **R2** | ✅ | Разбор: карточка + график LWC + сверка KS |
| **R3** | ✅ | Новости (+ ИИ-бейджи F-A: classify / hide noise) |
| **R4** | ✅ | Сделки / календарь |
| **UI Day** | ✅ | Вкладка «День» ≈ ваниль по плотности/иерархии (не полный редизайн) |

### Не в React-MVP

- Переписывать Python/API  
- Удалять ванильный HTML / папку `Portfolio_News`  
- G / H / IDEA-023/024 / чат  

---

## 8. Нельзя (жёстко)

- Торговля / write API / «покупай-продавай»  
- Секреты и `.env` в git  
- Выдуманный cash-эскроу  
- ~~React-рерайт дашборда~~ → **разрешён в `react_Portfolio_News/`; ваниль не сносить**  
- Платный API «вместо» SmartLab/ЦБ без решения  
- Прыгать в чат до A→B (ваниль); в React — чат не в MVP  
- IDEA-023/024 без команды  
- Ломать/переименовывать `dashboard-demo.html` без явной команды «выпиливаем ваниль»

---

## 9. Ключевые файлы кода

| Зона | Файлы |
|------|--------|
| UI ваниль | `portfolio_news/static/dashboard-demo.html` |
| UI React | sibling `react_Portfolio_News/` → `dist/` на `/app/` |
| API | `portfolio_news/api.py` |
| Сверка | `review_facts.py`, `fundamentals_smartlab.py`, `bonds_dohod.py`, `funds_cbr_ter.py` |
| График | `chart_cache.py` (SQLite hit сразу; stale/cold recent → ISS full в фоне), LWC в dashboard / React `PriceChart` |
| Новости / ИИ | `poll_job.py`, `/api/news`, `ai_noise.py`, `ai_ticker.py`, кэши AI |
| Конфиг | `config.py`, `.env` (локально) |

Технические простыни по слоям (если агенту надо копать): `docs/parts/10-*.md`, `11-*.md`, `08-*.md` — **не обязательны тебе**, если открыт этот MAP.

---

## 10. Как читать этот файл через месяц

1. §2 — живы ли мы  
2. §6 — что следующее  
3. §7 — справка F; **§7N** — лента; **§7F** — polish ИИ; **§7S** — allowlist каналов; **§7P** — privacy (план); **§7G** — авто-watch  
4. §4 — что уже ✅  

Всё. Не надо сверять три документа.
