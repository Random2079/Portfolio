# 🔧 Player theater / fullscreen — слой D5 (карточка №3)

| | |
|---|---|
| **Код** | [`../../Subtitle_App.py`](../../Subtitle_App.py) — `_toggle_player_theater`, `_on_theater_escape`, `_toggle_os_fullscreen`, `theater_btn` |
| **Слой** | D5 · карточка №3 |
| **Статус** | ✅ |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

---

## 🎯 Зачем

Fullscreen **внутри** YouTube в QWebEngineView не разворачивает окно приложения. Нужен свой «театр» на уровне Qt.

## Сделано

| Что | Как |
|-----|-----|
| Кнопка ⛶ | `theater_btn` в шапке плеера |
| Театр | скрыть сайдбар / chrome-виджеты, web_view на область |
| Esc | выход из театра |
| T | hotkey театра (F занят YouTube) |
| F11 | OS fullscreen окна |

## 🔍 Проверка

1. Плеер → ⛶ → сайдбар пропал.  
2. Esc или повтор ⛶ → сайдбар вернулся.  
3. T / F11 по подсказкам в tooltip.  
4. Fullscreen-кнопка **внутри** YouTube — можно игнорировать.

## ⚠️ Ограничения

- Это режим приложения, не DRM-кино на второй монитор.  
- Не ломать `_unload_player` при «Назад».
