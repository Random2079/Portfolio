# Part 18 — Авто-плотность Фона (IDEA-025)

| | |
|---|---|
| **Код** | Только [`../../overlay_player.py`](../../overlay_player.py) |
| **Слой** | IDEA-025 · карточка TZ №20 · A0–A2 |
| **Статус** | ⬜ ТЗ готово · код нет |
| **Канон очереди** | [`../../MAP.md`](../../MAP.md) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) · [polish 16](16-overlay-ux-polish.md) |

Команда: `делаем A0` → `делаем A1` → `делаем A2` (по одному).

---

## Зачем

Руками: полное окно → Ctrl+O → крутить «Плотность». Хочется: включил трек, отвернулся к Cursor — Фон сам ушёл в «стекло», клики в работу.

---

## MVP (поведение)

| Условие | Действие |
|---------|----------|
| Stage (полное окно) + playing + галка «Авто-плотность» | Старт idle-таймера |
| Idle `auto_density_idle_sec` (дефолт **4**) без мыши по кадру | Вкл сквозь + слайдер → `auto_density_pct` (дефолт **45**) → `_apply_stage_opacity` |
| Mouse move/click по кадру, Esc, ручной выкл сквозь, выход в каталог, stop | Стоп таймера; если был авто-CT — выкл сквозь (как Esc), плотность слайдера **не** затирать (prefs) |
| Каталог / не playing | Авто не активен; opacity 100% как сейчас |

**Контракт (не ломать):** `_apply_stage_opacity` — `% < 100` только при `_click_through`. Авто **сначала** сквозь, потом %.

---

## Слои

| Слой | Статус | Что в коде |
|------|--------|------------|
| **A0** | ⬜ | Prefs + UI Настр. (`auto_density`, `auto_density_pct`, `auto_density_idle_sec`). Без таймера. |
| **A1** | ⬜ | `QTimer` idle; на fire → CT + pct; хук play/pause/stage/catalog. |
| **A2** | ⬜ | Сброс на mouse (eventFilter кадра); не мигать на `setSource`/смене трека (`_hold_stage_opacity` учесть). |

---

## Точки входа (куда смотреть)

| Что | Где |
|-----|-----|
| Prefs load/save | `load_overlay_prefs` / `save_overlay_prefs` |
| Настр. UI | `OverlaySettingsDialog` |
| Поставить opacity | `_apply_stage_opacity`, `_apply_catalog_opacity` |
| Сквозь | `_set_click_through`, `_toggle_click_through` |
| Play/pause/stage | `_toggle_play`, `_enter_stage`, `_enter_catalog`, playback state |
| Мышь по кадру | `eventFilter` на `video` / `pulse` / `media_stack` |

Не нужна карта всего файла — только эта связка.

---

## Не делаем (в этом part)

- Отдельный процесс / wallpaper ОС
- Авто по яркости экрана / ML
- Плотность в каталоге
- Правки `Subtitle_App.py`, SMTC, хоткеев списка
- Менять смысл Ctrl+[ / слайдера вручную (ручной override ок)

---

## Проверка

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator
python overlay_player.py
# или: python Subtitle_App.py → 🎞 Фон
```

**A0:** Настр. → Авто-плотность вкл, 45%, 4с → OK → снова Настр. → те же значения.

**A1:** Полное окно + play → не двигать мышь 4с → сквозь + ~45%. Ctrl+O / Esc → управление обратно.

**A2:** После авто — свайп мыши по кадру не должен «дёргать» opacity при next track; каталог снова 100%.

**Регрессия:** клик/2× по кадру; ручной слайдер + Ctrl+O без галки авто; play when hidden.
