# PROMPT — YouTube_Translator (Agent)

Проект: `C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator`

## Перед кодом

1. [`MAP.md`](../MAP.md) — очередь и план слоя.  
2. [`docs/TZ.md`](TZ.md) — цель, карточки, «Не делаем».  
3. Нужный part из [`docs/parts/INDEX.md`](parts/INDEX.md).  
4. Не ломай: `_unload_player()`, yt-dlp через `python -m yt_dlp`, soft-lock окна (не `min==max`), single-instance если есть.

## Текущий фокус

**№9 / IDEA-021 F0** — список `dist/субтитры_*` + проводник ✅ (кнопка **📁 dist**).  
Дальше: `делаем F1` (delete/rename) или `делаем A0` (авто-плотность 025).

Карточка №1 и сайдбар ✅ — не переписывать с нуля.

## Статус карточек (кратко)

| № | Что | Статус |
|---|-----|--------|
| 1–8 | ИИ / UX / театр / закладки / Snap / split / музыка / motion | ✅ |
| **9** | **IDEA-021 dist** | **🟡 F0** |
| 10 | IDEA-022 Фон | 🟡 |
| 13–18 | Overlay polish | ✅ |
| 19 | UI backup | 🟡 |
| 20 | Авто-плотность | ⬜ |

## Не делаем

- Полный Chrome-клон; авто-ИИ без клика; IDEA-021 без команды; IDEA-025 без `делаем A*`; коммит/пуш без просьбы (пуш); % без сквозь.

## Стек

Боевой GUI: **PySide6 + QtWebEngine** (не CustomTkinter).

## Git

Не коммить и не пушить без явной просьбы.

## Запуск

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator
python Subtitle_App.py
# или wscript launch.vbs
```

**Код не писать**, пока пользователь не сказал «делаем» / «погнали» по конкретной карточке.
