# 🎞↓ Обои mp4+mp3 в YouTube_DL

| | |
|---|---|
| **Код** | [`../../Subtitle_App.py`](../../Subtitle_App.py) — `download_overlay_media`, кнопки **🎞↓** |
| **Слой** | M+ / IDEA-022 feed |
| **Статус** | ✅ MVP |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) · [MAP](../../MAP.md) · [музыка MP3](10-music-download.md) · [Фон](12-overlay-music.md) |

---

## Зачем

Каталог для **🎞 Фон** наполняли вручную (`_скачать_yt.bat` / чат). Теперь: вставил URL в SR → **🎞↓** → `mp4`+`mp3` с одним stem в `Music\YouTube_DL`.

## Поведение

| Где | Кнопка |
|-----|--------|
| Экран скачивания | **🎞↓** — URL из поля |
| Плеер | **🎞↓** — текущий ролик (WebView / folder id) |

Пайплайн (как bat):

1. `yt-dlp --impersonate Chrome-136` + cookies (`~/.subtitle_ripper/` или `Music\YouTube_DL\www.youtube.com_cookies.txt`)
2. mp4: **канон max** `bestvideo*[height<=2160]+bestaudio/…` + `-S res,fps,vbr,abr` ([part 21 C0](21-overlay-catalog-quality.md)); при «Only images» — retry DASH `299+140/…`
3. mp3: `-x --audio-format mp3 --audio-quality 0` (уже max) с тем же `-o … [%(id)s].%(ext)s`

Отмена — ✕ при busy (`overlay` / `overlay_player`).

Off impersonate: `SUBTITLE_RIPPER_IMPERSONATE=0`.

## Не в scope (этот слой)

- Автопоиск AMV по названию трека / «копилка» без URL
- Каталог-карточки / сортировка по дате → [part 21](21-overlay-catalog-quality.md)

## Проверка

```powershell
cd YouTube_Translator
python -m pytest test_overlay_download.py -q
# UI: URL → 🎞↓ → пара файлов в Music\YouTube_DL → 🎞 Фон играет
```
