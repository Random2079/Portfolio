# MAP — YouTube_Translator

Канон статуса / очереди / плана. Техника — `docs/TZ.md` + `docs/parts/`.
Дизайн UI (тема / motion) — `~/.cursor/skills/ui-design/profiles.md` + блок ниже.

| | |
|---|---|
| **Где мы** | Catalog: **C0+C1+C2b+C2c ✅** · кнопка Папка убрана (всегда YouTube_DL) · C3 по запросу ([part 21](docs/parts/21-overlay-catalog-quality.md)). |
| **Фокус** | C3 random — по запросу |
| **Код scope** | `overlay_player.py` |

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
| **1** | **C0** 🎞↓ max quality (+ статус/лог факта) | ✅ |
| **2** | **C1** каталог: сортировка дата старый→новый | ✅ |
| **3** | **C2** тяжёлые карточки | ❌ откат |
| **4** | **C2b** удалить/переименовать | ✅ ПКМ / F2 / Del |
| **5** | **C2c** мини-проводник: кадр+дата+бейджи | ✅ 1A/2A/3A |
| **6** | **C3** random / shuffle | ⏸ по запросу |
| — | Наушник multi-tap + SMTC | ⏸ (новые наушники) |
| — | 025 B0 авто-плотность комфорт | ⏸ |
| — | 🎞↓ обои mp4+mp3 MVP | ✅ part 20 |
| — | YT adblock в плеере | ✅ |
| — | 021 F1 delete/rename (`dist/`) | ⬜ отдельно от Фон C2b |

План/ТЗ чанков: [`docs/parts/21-overlay-catalog-quality.md`](docs/parts/21-overlay-catalog-quality.md).

---

## Аудит качества 🎞↓ (кратко)

| | Сейчас | Цель |
|--|--------|---------|
| Video | `bestvideo*[height<=2160]+bestaudio` + `-S res,fps,vbr,abr` | ✅ C0 |
| Audio mp3 | `--audio-quality 0` | оставить |
| Список Фон | `catalog_sort=date_asc` (mtime) | ✅ C1 |
| UI | QList текст | C2: пара + превью · C2b: del/rename |

---

## Смоук / план авто-плотности

Канон B0→B3: [`docs/parts/18-overlay-auto-density.md`](docs/parts/18-overlay-auto-density.md) — **⏸** пока catalog C*.

---

## Запреты

- Плотность `<100%` только со сквозь.
- Пуш только по просьбе.
- Не возвращать morph size+pos на shell; не /embed/ top-level (Error 153).
- Не склеивать C0+C1+C2+C2b в один проход.
