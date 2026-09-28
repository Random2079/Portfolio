# 🔧 Player theater / fullscreen — слой D5 (карточка №3)

| | |
|---|---|
| **Код** | [`../../Subtitle_App.py`](../../Subtitle_App.py) — `_enter_immersive_playback`, `_exit_player_theater`, `theater_btn` |
| **Слой** | D5 · карточка №3 |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

---

## 🎯 Зачем

Fullscreen **внутри** YouTube embed не разворачивает окно приложения. Нужен свой полный экран на уровне Qt.  
Плеер при этом — **обычное окно** (ресайз / max / snap / 2 монитора); компактный fixed только на экране скачивания.

## Сделано

| Что | Как |
|-----|-----|
| Кнопка ⛶ | `theater_btn` в шапке плеера |
| F / F11 | `ApplicationShortcut` → `showFullScreen()` + спрятать chrome |
| Esc | выход из fullscreen, вернуть geometry |
| Плеер-окно | `_apply_free_shell_size` — min/max/close, тянуть края, Aero Snap |

## 🔍 Проверка

1. Плеер → тянуть края / Win+← / перетащить на 2-й монитор.  
2. F или ⛶ → весь монитор, панели скрыты.  
3. Esc / F снова → обратно в оконный режим.  
4. «Назад» → снова compact 640×400 без max.

## ⚠️ Ограничения

- Не ломать `_unload_player` при «Назад».  
- Download shell остаётся fixed (без max).
