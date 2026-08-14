# IDEA-013 — Micro wife (свой женский голос)

## Цель

Нормальный **женский** голос для Cursor TTS. Piper-Ирина не зашла. Рабочее имя: **micro wife**.

## Статус

**Готово пока (2026-08-15).** Жить на Kokoro (день) + Qwen (качество). Дальше — только по явной команде.

## Железо

i5-12450H / 16 GB / **RTX 3050 4 GB**

## Что в проде

| Движок | Роль |
|--------|------|
| **Kokoro-ru** | Быстрый локальный (CPU worker 3.12), голоса Света / Маша / Дима |
| **Qwen 0.6B** | Лучшее качество; `faster-qwen3-tts` BF16 + SDPA + CUDA graphs |

Edge / Silero / Piper из каталога убраны.

## Сделано

- [`Cursor_TTS/micro_wife/`](../../Cursor_TTS/micro_wife/) — Qwen + prototypes + designs  
- [`Cursor_TTS/speak_kokoro.py`](../../Cursor_TTS/speak_kokoro.py) + `kokoro_worker.py`  
- Панель: два движка; README обновлён  
- Эксперимент Triton/TurboQuant: изолированно, на 3050 ~2× медленнее baseline — не вшивать  

## Не в scope сейчас

- Neuro-агент (IDEA-001)  
- Клон с чужих аудиокниг  
- Аренда GPU / 1.7B VoiceDesign  
- Повторный разгон Qwen без команды  

## Установка

См. [`Cursor_TTS/README.md`](../../Cursor_TTS/README.md) и [`micro_wife/README.md`](../../Cursor_TTS/micro_wife/README.md).
