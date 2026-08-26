# 🔧 DeepSeek ИИ-разбор — слой C

| | |
|---|---|
| **Код** | [`../../ai_analyze.py`](../../ai_analyze.py) |
| **Слой** | C |
| **Статус** | ✅ (логика API) · UX — карточки №1–2 |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

---

## 🎯 Зачем

Текст субтитров → DeepSeek → JSON → `ai_analysis.json` (+ legacy `ai_highlights.json`) рядом с роликом в `dist/`.

## Режимы

| mode | Промпт | Смысл |
|------|--------|-------|
| `invest` | Чекпоинт пользователя | Фильтр: ignore / hold_context / verify_primary; **не** buy/sell |
| `general` | Краткий обзор | verdict, summary, takeaways, highlights |

## Вход / выход

- **Вход:** папка ролика; предпочтительно `1_текст_с_таймкодами.txt`, иначе `0_весь_текст_для_буфера.txt` (обрезка в коде).
- **Выход:** `ai_analysis.json` в той же папке.
- **Cancel:** `cancel_event` → `AnalyzeCancelled`.

## Вызов из GUI

`Subtitle_App.on_ai_analyze` → поток → `analyze_subtitles(folder, mode=..., cancel_event=...)` → `_done_signal` с префиксом `__ai__`.

## 🔍 Проверка

```powershell
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator
python -c "from ai_analyze import analyze_subtitles; print(analyze_subtitles(r'dist\субтитры_...', mode='general'))"
```

(Подставь реальную папку из `dist/`.)

## ⚠️ Ограничения

- Ключ API сейчас в файле — вынос в env не блокер №1.  
- Не выдумывать факты — system prompt.
