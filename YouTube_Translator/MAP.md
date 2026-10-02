# MAP — YouTube_Translator

Канон статуса / очереди / плана. Техника — `docs/TZ.md` + `docs/parts/`.
Дизайн UI (тема / motion) — `~/.cursor/skills/ui-design/profiles.md` + блок ниже.

| | |
|---|---|
| **Где мы** | Фокус: **Фон catalog C0–C3** ([part 21](docs/parts/21-overlay-catalog-quality.md)). Наушник multi-tap — **⏸**. |
| **Фокус** | **`делаем C0`** — max quality 🎞↓ · потом C1 дата · C2 карточки · C3 random |
| **Код scope** | `Subtitle_App.py` (C0) · `overlay_player.py` (C1–C3) |

---

## Дизайн SR — закрыто (2026-09-28)

Не открывать заново без явной просьбы («бесит глаз» / новый превью-раунд).

| | Канон |
|---|---|
| Жанр | **Tool**, не лендинг |
| Тема | **Theme A Slate** (`configure_qt_theme`) |
| Переходы окон | **fade+center** (`fade_center_transition`) — не morph size+pos |
| Фон | fade-in при открытии; первый раз — центр |
| Превью | `docs/design-previews/` · выбор motion: `window-transition-types.html` → **3** |
| Профиль | `~/.cursor/skills/ui-design/profiles.md` |

Коммит motion: `664d44c`.

---

## Очередь

| # | Что | Статус |
|---|-----|--------|
| **1** | **C0** 🎞↓ max quality (+ статус/лог факта) | ⬜ **следующий** |
| **2** | **C1** каталог: сортировка дата старый→новый | ⬜ |
| **3** | **C2** каталог: карточки пары mp4/mp3 + thumb + title | ⬜ |
| **4** | **C3** random / shuffle | ⏸ после C1–C2 |
| — | Наушник multi-tap + SMTC | ⏸ (новые наушники) |
| — | 025 B0 авто-плотность комфорт | ⏸ |
| — | 🎞↓ обои mp4+mp3 MVP | ✅ part 20 |
| — | YT adblock в плеере | ✅ |
| — | 021 F1 delete/rename | ⬜ |

План/ТЗ чанков: [`docs/parts/21-overlay-catalog-quality.md`](docs/parts/21-overlay-catalog-quality.md).

---

## Аудит качества 🎞↓ (кратко)

| | Сейчас | Цель C0 |
|--|--------|---------|
| Video | `bv*+ba/b` (+ DASH retry) | явный max + format-sort; не ниже текущего |
| Audio mp3 | `--audio-quality 0` | оставить |
| Список Фон | алфавит | C1: mtime asc |
| UI | QList текст | C2: пара + превью |

---

## Смоук / план авто-плотности

Канон B0→B3: [`docs/parts/18-overlay-auto-density.md`](docs/parts/18-overlay-auto-density.md) — **⏸** пока catalog C*.

---

## Запреты

- Плотность `<100%` только со сквозь.
- Пуш только по просьбе.
- Не возвращать morph size+pos на shell; не /embed/ top-level (Error 153).
- Не склеивать C0+C1+C2 в один проход.
