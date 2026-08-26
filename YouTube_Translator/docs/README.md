# docs/ — карта для агента

ТЗ и parts лежат **здесь**, не в корне рядом с `.py` (IDEA-020).

| Файл | Роль |
|------|------|
| [TZ.md](TZ.md) | Цель, карточки №1–10, слои, «не делаем», проверка |
| [PROMPT_FOR_AGENT.md](PROMPT_FOR_AGENT.md) | Блок для нового чата |
| [parts/INDEX.md](parts/INDEX.md) | Список parts |

## Part ↔ код

| Part | Код |
|------|-----|
| 01 AI sidebar | `Subtitle_App.py` (player sidebar, tabs, busy) |
| 02 DeepSeek | `ai_analyze.py` |
| 03 Launch | `launch.vbs`, `launch/run.vbs`, `requirements.txt` |
| 04 Theater | `Subtitle_App.py` (`_toggle_player_theater`, …) |
| 05 Bookmarks | `Subtitle_App.py`, `bookmarks.json` |
| 06 Motion | `ui_motion.py` + wiring в `Subtitle_App.py` |
| 07 **ИИ текущего ролика (№1)** | `Subtitle_App.py` (`on_ai_analyze` ↔ WebView URL) |
| 08 Split / cancel | `Subtitle_App.py` (📥 / ✨ / ✕) |
| 09 Window / Snap | `Subtitle_App.py` (soft-lock) |
| 10 Music | `Subtitle_App.py` (audio yt-dlp) |
| 11 Parked 021 / статус 022 | `IDEAS.md` · 022 → part 12 |
| 12 Overlay (IDEA-022) | `overlay_player.py`, кнопка «Фон» в `Subtitle_App.py` |

Вход для человека (быстрый старт): [../README.md](../README.md).
