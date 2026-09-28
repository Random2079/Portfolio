# Part 18 — Авто-плотность Фона (IDEA-025)

| | |
|---|---|
| **Код** | Только [`../../overlay_player.py`](../../overlay_player.py) |
| **Слой** | IDEA-025 · карточка TZ №20 · A0–A2 |
| **Статус** | A0 ✅ · A1 ✅ · A2 ✅ · A3 ✅ |
| **Канон очереди** | [`../../MAP.md`](../../MAP.md) |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) · [polish 16](16-overlay-ux-polish.md) |

Команда: `делаем A0` → `делаем A1` → `делаем A2` → `делаем A3` (по одному).

---

## Зачем

Руками: полное окно → Ctrl+O → крутить «Плотность». Хочется: включил трек, отвернулся к Cursor — Фон сам ушёл в «стекло», клики в работу. На светлом столе анимацию плохо видно → плотнее; на тёмном слишком кричит → прозрачнее.

---

## MVP (поведение)

| Условие | Действие |
|---------|----------|
| Stage (полное окно) + playing + галка «Авто-плотность» | Старт idle-таймера |
| Idle `auto_density_idle_sec` (дефолт **4**) без мыши по кадру | Вкл сквозь + % от яркости стола/обоев (база `auto_density_pct` ±22) → `_apply_stage_opacity` |
| Mouse move/click по кадру, Esc, ручной выкл сквозь, выход в каталог, stop | Стоп таймера; если был авто-CT — выкл сквозь (как Esc), плотность слайдера **не** затирать (prefs) |
| Каталог / не playing | Авто не активен; opacity 100% как сейчас |

**Контракт (не ломать):** `_apply_stage_opacity` — `% < 100` только при `_click_through`. Авто **сначала** сквозь, потом %.

**A3 яркость:** сэмпл экрана вне окна Фона; если почти fullscreen → файл обоев Windows. Светлый → выше %; тёмный → ниже %. Нет данных → база prefs.

---

## Слои

| Слой | Статус | Что в коде |
|------|--------|------------|
| **A0** | ✅ | Prefs + UI Настр. (`auto_density`, `auto_density_pct`, `auto_density_idle_sec`). |
| **A1** | ✅ | `QTimer` idle; на fire → CT + pct; хук play/stage/catalog/pause. |
| **A2** | ✅ | Hold при next track; авто-% не в `stage_opacity` prefs; выход CT → вернуть ручной %; каталог 100%. |
| **A3** | ✅ | На fire: `%` от яркости стола/обоев (база ± span). |

---

## Точки входа (куда смотреть)

| Что | Где |
|-----|-----|
| Prefs load/save | `load_overlay_prefs` / `save_overlay_prefs` |
| Настр. UI | `OverlaySettingsDialog` |
| Яркость стола / обои | `_desktop_luminance_outside`, `_wallpaper_luminance`, `_resolve_auto_density_pct` |
| Поставить opacity | `_apply_stage_opacity`, `_apply_catalog_opacity` |
| Сквозь | `_set_click_through`, `_toggle_click_through` |
| Play/pause/stage | `_toggle_play`, `_enter_stage`, `_enter_catalog`, playback state |
| Мышь по кадру | `eventFilter` на `video` / `pulse` / `media_stack` |

Не нужна карта всего файла — только эта связка.

---

## Не делаем (в этом part)

- Отдельный процесс / ML / камера
- Плотность в каталоге
- Правки `Subtitle_App.py`, SMTC, хоткеев списка
- Менять смысл Ctrl+[ / слайдера вручную (ручной override ок)
- Пересчёт яркости каждые N сек пока уже в CT (только на fire)

---

## Проверка

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator
python overlay_player.py
# или: python Subtitle_App.py → 🎞 Фон
```

**A0:** Настр. → Авто-плотность вкл, 45%, 4с → OK → снова Настр. → те же значения.

**A1:** Полное окно + play → не двигать мышь 4с → сквозь + ~%. Ctrl+O / Esc → управление обратно.

**A2:** После авто — next track без мигания 100%; каталог снова 100%.

**A3:** Светлые обои → статус `%` выше базы; тёмные → ниже. Статус вида `Авто-плотность 58% (обои светлый)`.

**Регрессия:** клик/2× по кадру; ручной слайдер + Ctrl+O без галки авто; play when hidden.
