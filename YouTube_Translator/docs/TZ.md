# 📋 YouTube Translator — Subtitle Ripper Pro

| | |
|---|---|
| **Код** | `YouTube_Translator/` — `Subtitle_App.py`, `ai_analyze.py`, `ui_motion.py`, `timecode_player.py`, `overlay_player.py` |
| **ТЗ** | `YouTube_Translator/docs/TZ.md` ← этот файл |
| **Bootstrap** | IDEA-020 (docs отдельно от `.py`) · дата актуализации 2026-08-26 |
| **Связь** | IDEA-010/011 ✅ · IDEA-016 ✅ · IDEA-021 ⬜ парковка · IDEA-022 🟡 MVP (в Translator) |

> Боевой GUI: **PySide6 + QWebEngine** (не CustomTkinter).  
> Скачивание субтитров + встроенный YouTube + сайдбар ИИ уже в бою.  
> Этот документ — **карта карточек/слоёв** и критерии «готово»; код по ним писать только после «делаем».

---

## 🎯 Цель

Одно приложение: вставил ссылку / смотришь ролик во встроенном плеере → субтитры в `dist/` → кнопкой **✨ ИИ** получаешь разбор **именно того ролика, что сейчас на экране** (режимы Инвест/Обычный, вкладки Разбор / ИИ-моменты / Все), плюс удобные соседние фичи (театр, закладки, музыка, отмена, motion).

---

## 📇 Карточки (пользовательский бэклог)

Нумерация зафиксирована из чата (2026-08-26): «составляй ТЗ по всем этим» + явное **«На кар №1»**.

| № | Карточка | Слой | Статус | Суть |
|---|----------|------|--------|------|
| **1** | **ИИ по текущему ролику в плеере** | D1+ / C | ✅ | Смотришь видео → **✨ ИИ** → разбор **этого** id; субы из `dist/` или авто-скачивание → ИИ |
| 2 | UX сайдбара ИИ | D | ✅ | Статус busy, табы Разбор / ИИ-моменты / Все, restore `ai_analysis.json` |
| 3 | Театр / immersive | D5 | ✅ | ⛶ скрыть сайдбар; Esc / T; F11 OS fullscreen |
| 4 | Закладки + Cloudflare honesty | F | ✅ | Aniwaves; если WebView режет — «Открыть в Chrome» `--app=` |
| 5 | Мягкий размер окна / Aero Snap | W | ✅ | Download 580×380 soft-lock; плеер/закладки — resize + Snap; clamp on-screen |
| 6 | Split 📥 vs ✨ ИИ + Отмена | D6 | ✅ | 📥 = субы текущего URL без ИИ; ✨ = разбор текущего id; ✕ Отмена видна при busy |
| 7 | Скачивание музыки (MP3) | M | ✅ | Кнопка на download и в плеере → `Music\YouTube_DL` |
| 8 | ui_motion (микроанимации) | G | ✅ | Hover/press + BusyPulse на Скачать / ИИ |
| 9 | Файлы `dist/` внутри приложения | IDEA-021 | ⬜ парковка | Список / копировать / переименовать / удалить — **не стартовать** без команды |
| 10 | Overlay музыка/mp4 поверх окон | IDEA-022 | 🟡 MVP | Кнопка **🎞 Фон** → `overlay_player.py`: каталог, play+визуал, opacity, click-through |

Легенда: ✅ сделано в коде · 🟡 частично / есть gap · ⬜ не начато / парковка.

---

## 📊 MVP / технические слои (буквы)

| Слой | Статус | Описание |
|------|--------|----------|
| A — Скачивание субтитров + Qt GUI | ✅ | yt-dlp (`python -m yt_dlp`), `dist/субтитры_<title> [id]/ |
| B — Встроенный YouTube (WebView) | ✅ | полный `youtube.com/watch`, `yt_profile`, seek |
| C — DeepSeek ИИ-разбор | ✅ | `ai_analyze.py` → `ai_analysis.json` (+ highlights) |
| D — UX сайдбара ИИ | ✅ | табы, busy pulse, cancel ИИ, restore JSON |
| **D1+ — ИИ = текущий ролик (карточка №1)** | **✅** | `on_ai_analyze` → URL WebView → folder / скачать субы → ИИ |
| D5 — Театр / fullscreen | ✅ | ⛶, Esc, T, F11 |
| D6 — Split 📥 / ✨ + Отмена | ✅ | 📥 без ИИ; ✨ синхронизирует текущий id (карточка №1) |
| W — Размер окна / Snap / clamp | ✅ | soft-lock download; не ломать `WS_THICKFRAME` |
| M — Музыка MP3 | ✅ | download + player |
| F — Закладки | ✅ | `bookmarks.json`, Chrome `--app=` fallback |
| G — ui_motion | ✅ | `ui_motion.py` |
| E — «Полный браузер-клон» | 🚫 | **не в scope** |
| IDEA-021 | ⬜ | парковка в `IDEAS.md` |
| IDEA-022 overlay | 🟡 | MVP: `overlay_player.py` + кнопка «Фон» |

---

## 🃏 Карточка №1 — ИИ по текущему ролику (детально)

### Зачем (слова пользователя)

> Ролик который **текущий** я смог там же нажать кнопку ИИ и сделать обзор по **этому** ролику.

Скрин: плеер + сайдбар Разбор / ИИ-моменты / Все, режимы Инвест/Обычный, вердикт — это **целевой UX**. Не новый экран.

### Было / стало (карточка №1)

| Было (gap) | Стало |
|------------|--------|
| `✨` бил в stale `_current_player_folder` | `✨` → `_get_current_youtube_url` → id из WebView |
| Навигация A→B в WebView → разбор A | Папка B / скачивание B, затем ИИ по B |
| Нет субов → «открой плеер» / чужой folder | `_pending_ai_after_subs`: скачать как 📥 → `_start_ai_analyze_folder` |

### Целевое поведение (done)

1. В плеере на экране ролик **X** → жмёшь **✨ ИИ** → разбор про **X** (id из WebView или синхронизированный folder).
2. Если папка `dist/субтитры_* [idX]` есть — берём `1_текст_с_таймкодами.txt` / `0_…` (как сейчас `analyze_subtitles`).
3. Если папки нет — **понятный статус** («скачиваю субы…» / «нет субтитров») и либо авто-скачивание как у 📥, затем ИИ, либо явный отказ без молчаливого анализа чужого folder.
4. Режимы **Инвест / Обычный** влияют на промпт; визуально активный режим виден.
5. После ответа: вкладка **Разбор** (вердикт/вывод), **ИИ-моменты**, **Все**; статус внизу; `ai_analysis.json` в папке **этого** ролика.
6. Busy: кнопка «ИИ…» + пульс + ✕ Отмена; повторный клик не плодит гонки (job id / cancel).

### Не путать

- **📥** — только субтитры/таймкоды текущего URL, **без** DeepSeek.
- **✨ ИИ** — разбор (DeepSeek); может сначала убедиться, что субы текущего id на месте.
- Скачивание с главного экрана («Скачать») — по URL из поля ввода; это не отменяет карточку №1.

---

## ❌ Не делаем (scope lock)

- Полноценный Chrome-клон (вкладки на весь интернет, расширения, sync).
- Авто-ИИ при каждом открытии плеера / смене URL без клика.
- Переписывание GUI с нуля / возврат на CustomTkinter как боевой UI.
- Реализация IDEA-021 без явной команды; IDEA-022 MVP уже в коде (`overlay_player.py`) — не раздувать без запроса.
- Торговые сигналы buy/sell «с ролика» (запрет уже в промпте invest).
- Коммит/пуш без просьбы пользователя.
- Вынос API-ключа в env — можно позже, не блокер карточки №1.

**Задумка «всё как Chrome»** — слой E, мысли; не делать.

---

## ✅ Готово когда

### Карточка №1 (обязательный чеклист)

- [x] В плеере открыт ролик A (есть `dist/…[idA]`), жмёшь ✨ → разбор A.
- [x] В том же WebView переходишь на ролик B (или открываешь B без копирования URL в поле ввода), жмёшь ✨ → разбор **B**, не A.
- [x] Для B без папки в `dist/` — статус «ИИ: скачиваю субтитры…» → затем ИИ; без анализа чужой папки.
- [x] Инвест и Обычный дают разный HTML-разбор; табы Разбор / ИИ-моменты / Все работают.
- [x] Cancel во время ИИ останавливает; busy pulse гаснет; новый запрос не путает ответы.
- [x] `ai_analysis.json` лежит в папке разобранного id; повторное открытие плеера подтягивает сохранённое.

### Остальные карточки 2–8

- [x] Считаются закрытыми по коду на момент ТЗ (регрессии ловить при правках №1).
- [ ] После фикса №1 — smoke: театр, закладки, музыка, soft-lock, motion не сломаны.

### Парковка 9 / статус 10

- №9 IDEA-021 — парковка, не в «готово».
- №10 IDEA-022 — MVP 🟡 (см. [12-overlay-music.md](parts/12-overlay-music.md)); допил по запросу.

---

## 🔍 Проверка

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator
pip install -r requirements.txt
# Боевой стек — PySide6 (+ QtWebEngine). requirements.txt может отставать — доустановить при необходимости.
python Subtitle_App.py
# или: wscript launch\run.vbs  /  wscript launch.vbs
```

**Карточка №1**

1. Скачать субы ролика A → Плеер → ✨ ИИ (Обычный) → сайдбар «Обычный разбор», статус с вердиктом.
2. В WebView открыть другой ролик B (рекомендации / поиск) → ✨ ИИ → убедиться, что текст про B; папка `dist/…[idB]`.
3. Ролик C без субов → ✨ → либо скачивание+разбор, либо ясный отказ; **не** тихий разбор A.
4. Инвест → другие поля (action / flags); ✕ Отмена на mid-flight.

**Регрессия**

5. ⛶ / Esc / T / F11; 🔖 Закладки + Chrome fallback; 🎵 MP3; **🎞 Фон** overlay; экран скачивания soft-lock + Snap в плеере.

---

## 📁 docs/parts/

| # | Part | Код | Карточка / слой |
|---|------|-----|-----------------|
| 01 | [01-ai-sidebar-ux.md](parts/01-ai-sidebar-ux.md) | `Subtitle_App.py` | №2 / D |
| 02 | [02-ai-analyze-deepseek.md](parts/02-ai-analyze-deepseek.md) | `ai_analyze.py` | C |
| 03 | [03-launch-and-deps.md](parts/03-launch-and-deps.md) | `launch*`, `requirements.txt` | A |
| 04 | [04-player-theater-fullscreen.md](parts/04-player-theater-fullscreen.md) | `Subtitle_App.py` | №3 / D5 |
| 05 | [05-bookmarks-vision.md](parts/05-bookmarks-vision.md) | `Subtitle_App.py`, `bookmarks.json` | №4 / F |
| 06 | [06-button-motion-vision.md](parts/06-button-motion-vision.md) | `ui_motion.py` | №8 / G |
| 07 | [07-player-ai-current-video.md](parts/07-player-ai-current-video.md) | `Subtitle_App.py`, `ai_analyze.py` | **№1 / D1+** |
| 08 | [08-split-download-ai-cancel.md](parts/08-split-download-ai-cancel.md) | `Subtitle_App.py` | №6 / D6 |
| 09 | [09-window-size-snap.md](parts/09-window-size-snap.md) | `Subtitle_App.py` | №5 / W |
| 10 | [10-music-download.md](parts/10-music-download.md) | `Subtitle_App.py` | №7 / M |
| 11 | [11-parked-021-022.md](parts/11-parked-021-022.md) | 021 парковка · 022 → 12 | №9–10 |
| 12 | [12-overlay-music.md](parts/12-overlay-music.md) | `overlay_player.py`, `Subtitle_App.py` | №10 / IDEA-022 |

---

## 🤖 Новый чат

Вставь [`PROMPT_FOR_AGENT.md`](PROMPT_FOR_AGENT.md).  
Карта part ↔ код: [`docs/README.md`](README.md).

Карточка №1 закрыта в коде (2026-08-26). Новые слои — только после «делаем».
