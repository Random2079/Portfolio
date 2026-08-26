# PROMPT — YouTube_Translator (Agent)

Проект: `C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator`

## Перед кодом

1. Прочитай [`docs/TZ.md`](TZ.md) — цель, карточки, «Не делаем».  
2. Открой нужный part из [`docs/parts/INDEX.md`](parts/INDEX.md).  
3. Не ломай: `_unload_player()`, yt-dlp через `python -m yt_dlp`, soft-lock окна (не `min==max`), single-instance если есть.

## Текущий фокус

Карточка №1 (**ИИ по текущему ролику**) — ✅.  
Следующее — только после «делаем» (регрессии / IDEA-021/022 / новые карточки).

Сайдбар (табы, busy, режимы) уже ✅ — не переписывать с нуля.

## Статус карточек (кратко)

| № | Что | Статус |
|---|-----|--------|
| 1 | ИИ текущего ролика | ✅ |
| 2 | UX сайдбара | ✅ |
| 3 | Театр | ✅ |
| 4 | Закладки / Cloudflare | ✅ |
| 5 | Размер / Snap | ✅ |
| 6 | 📥 vs ✨ + Отмена | ✅ |
| 7 | Музыка | ✅ |
| 8 | ui_motion | ✅ |
| 9–10 | IDEA-021 / 022 | ⬜ парковка |

## Не делаем

- Полный Chrome-клон; авто-ИИ без клика; IDEA-021/022 без команды; коммит/пуш без просьбы.

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
