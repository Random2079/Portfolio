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
Плеер/закладки — обычное окно Windows: ресайз, **Aero Snap** (половина экрана), без улёта за край.

## Решение (важно)

**Не** фиксировать через `setMaximumSize` / `min==max` навсегда: это снимает `WS_THICKFRAME` / `WS_MAXIMIZEBOX`, и Snap умирает даже после «разблокировки».

Вместо этого: **мягкий** возврат размера download в `resizeEvent` (`_maybe_relock_download_window_size`).

| Режим | Поведение |
|-------|-----------|
| download | ~580×380 soft-lock |
| player / bookmarks | free resize, min ~360×280, clamp on-screen |

## 🔍 Проверка

1. Экран скачивания — размер стабилен.  
2. Плеер — тащи к краю → Snap на половину.  
3. Win+← / Win+→.  
4. Окно не оказывается целиком за экраном после смены режима.

## ⚠️ Ограничения

- Не возвращать жёсткий `setFixedSize` на download, если ломает Snap после unlock.
