# 🔧 Button motion / micro-animations — слой G (карточка №8)

| | |
|---|---|
| **Код** | [`../../ui_motion.py`](../../ui_motion.py) · wiring в [`../../Subtitle_App.py`](../../Subtitle_App.py) |
| **Слой** | G · карточка №8 |
| **Статус** | ✅ MVP |
| **Навигация** | [INDEX](INDEX.md) · [TZ](../TZ.md) |

---

## 🎯 Зачем

Понятная «живость» кнопок: hover/press и пульс во время долгой работы (скачивание / ИИ).

## Сделано

| Что | Как |
|-----|-----|
| Hover / press toolbar | `attach_button_motion` / `attach_many` — opacity ~150 ms |
| Пульс «Скачать» | `BusyPulse` + `motion_busy` при `_busy` |
| Пульс «✨ ИИ» | `BusyPulse` при `_ai_busy`, текст «ИИ…» |

## Не делали

- Lottie / полноценный motion design system.  
- Анимация кнопок таймкодов в сайдбаре.

## 🔍 Проверка

1. Hover/press на download / player — лёгкий dip.  
2. Скачивание субов — пульс.  
3. ИИ — «ИИ…» пульсирует, после ответа стоп.
