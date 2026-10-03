# Part 21 — Фон: качество 🎞↓ + каталог (пары / превью / дата)

| | |
|---|---|
| **Код** | [`../../Subtitle_App.py`](../../Subtitle_App.py) (`download_overlay_media`, fmt) · [`../../overlay_player.py`](../../overlay_player.py) (`scan_media`, список) |
| **Слой** | IDEA-022 catalog / M+ follow-up |
| **Статус** | ✅ C0 · ✅ C1 · ❌ C2 · ✅ C2b · ✅ C2c · ✅ C3 shuffle |
| **Канон очереди** | [`../../MAP.md`](../../MAP.md) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) · [part 20 🎞↓](20-overlay-wallpaper-download.md) · [Фон 12](12-overlay-music.md) |

Команда: (позже) `делаем C3`. Наушник multi-tap — **⏸**.

Решение UX: карточки C2 **откатили** (2026-10-03). Manage = **удалить/переименовать** в обычном списке (C2b ✅).

---

## Цель (канон)

1. **🎞↓** качает **максимально доступное** качество видео (+ mp3 best).  
2. В Фоне видно не «сырой проводник», а **карточки треков**: превью + название + что есть пара (mp4 / mp3).  
3. Порядок списка: **от старого к новому** (дата файла).  
4. Потом: **удалить** пару с диска + **переименовать** файлы (отображаемое имя = имя на диске).  
5. Позже: **случайный** трек / shuffle.

---

## Факт сейчас (аудит)

| Что | Как в коде | Заметка |
|-----|------------|---------|
| mp4 fmt | max ≤2160 + `-S` (C0 ✅) | статус WxH после качки |
| mp3 | `-x --audio-format mp3 --audio-quality 0` | уже max VBR |
| Список | `scan_media` → `date_asc` (C1 ✅) | prefs `catalog_sort` |
| Дубли | один `[youtubeId]` → предпочитает **видео** | пара mp3+mp4 схлопывается |
| UI списка | `QListWidget` текст | без превью / бейджей / manage |
| Папка | `QFileDialog` | диалог оставить вторичным |

---

## Чанки (лестница)

### C0 — Качество 🎞↓ → max ✅

**Сделано**
- `-f bestvideo*[height<=2160]+bestaudio/bestvideo*+bestaudio/best` + `-S res,fps,vbr,abr`
- DASH fallback с тем же max
- После качки: статус / return с `WxH · filename` (ffprobe)
- Тест: `test_overlay_download.py`; смоук Alan Walker Faded → **1920x1080**

---

### C1 — Порядок: дата старый → новый ✅

**Сделано**
- `scan_media(..., sort=)` — `date_asc` (канон) / `date_desc` / `name`
- Prefs `catalog_sort` (дефолт `date_asc`); `_reload_list` читает prefs
- Тест: `test_scan_media_sort.py` (mtime + dedupe)

---

### C2 — Каталог: карточки ❌ откат

Сделали и откатили (`8fe6728`): превью/бейджи оказались не тем UX. Список остаётся текстовым.

---

### C2b — Удалить + переименовать (диск) ✅

**Сделано**
- ПКМ → «Переименовать…» / «Удалить с диска…»
- **F2** rename · **Delete** delete (в каталоге)
- Пара по `[youtubeId]` (или stem); `[id]` сохраняется
- Тест: `test_catalog_manage.py`

---

### C2c — Мини-проводник в списке Фона ✅

Решение (2026-10-03): **1A 2A 3A** — не системный диалог «Папка», а вид списка как проводник.

**Сделано**
- Строка: маленький кадр · название · дата · бейджи `mp4`/`mp3`
- Одна строка = пара; rename/delete как C2b
- Thumbs в `%LOCALAPPDATA%\.subtitle_ripper\thumbs\` (очередь ffmpeg, без шторма консолей)
- Тест: `test_catalog_explorer.py`

Кнопка **Папка** по-прежнему только смена каталога (системный диалог).

---

### C3 — Случайный трек / shuffle ✅

**Сделано**
- Toggle shuffle на транспорте + prefs `catalog_shuffle` (и чекбокс в Настр.)
- **Ctrl+Shift+R** — разовый random (не текущий)
- Shuffle вкл: «след.» / Ctrl+Shift+1 / конец трека → random
- Тест: `test_catalog_shuffle.py` (`pick_random_playlist_index`)

---

## Зависимости чанков

```
C0 (качество) ── ✅
C1 (дата)     ── ✅
C2 (карточки) ── ❌ откат
C2b (manage)  ── ✅
C2c (explorer)── ✅ мини-проводник
C3 (random)   ── ✅
```

---

## Риски

| Риск | Митигация |
|------|-----------|
| Max fmt ломает «Only images» / storyboard | DASH fallback из part 20 |
| Thumbs жрут диск/CPU | Кэш по id; лениво; лимит размера |
| Mtime после rename «новый» | Ок для date_asc; later sidecar если бесит |
| Rename ломает `[id]` | Не трогать `[id]`; менять только title-часть |
| Delete без confirm | Всегда QMessageBox |
| Тяжёлый C2 | Сначала list+badge; превью вторым шагом внутри C2 |

---

## Не делаем без запроса

- Наушник multi-tap досмотр (⏸)
- Автопоиск AMV / копилка без URL
- Смена папки `YouTube_DL` на другое место по умолчанию
- Полный файловый менеджер / bulk / корзина
- «Открыть в проводнике» (пока явно не просили)

---

## Смоук общий (после C0–C2b)

1. 🎞↓ → max quality + mp3.  
2. Фон: старые сверху.  
3. Карточка: title + mp4/mp3 + thumb; play.  
4. Rename / delete пары на диске.  
5. Play/сквозь / плотность не трогаем.
