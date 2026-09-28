# 🔧 Размер окна / Aero Snap / clamp — слой W (карточка №5)

| | |
|---|---|
| **Код** | [`../../Subtitle_App.py`](../../Subtitle_App.py) — `_lock_download_window_size`, `_unlock_player_window_size`, `_ensure_window_on_screen`, `resizeEvent` / `moveEvent` |
| **Слой** | W · карточка №5 |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

---

## 🎯 Зачем

Экран скачивания — стабильный компактный размер («мертво одного размера»).  
Плеер/закладки — **обычное окно Windows**: ресайз, max, **Aero Snap**, перенос на второй монитор.

## Решение (важно)

**Download (2026-09-28):** фиксированный размер; кнопки **Свернуть** + **Закрыть** (без max):
- `CustomizeWindowHint` + Title + SystemMenu + Minimize + Close
- `setFixedSize` ~ **640×400** (clamp под экран)

**Player / закладки:** свободное окно:
- обычные флаги с **Maximize**
- старт ~ **1120×760** (clamp), дальше юзер тянет / snap / 2 монитора
- **F / F11 / ⛶** → `showFullScreen()`; Esc — выход

F11 / OS fullscreen на **download** — нет; на плеере — да.

## 🔍 Проверка

1. Download — размер fixed, есть − и ×, нет □ max.  
2. Плеер — можно тянуть края, max, Win+← / на 2-й монитор.  
3. F → полный экран; Esc → обратно.  
4. «Назад» → снова compact download.

## ⚠️ Ограничения

- Не возвращать жёсткий `setFixedSize` на download, если ломает Snap после unlock.
