# IDEA-013 — Micro wife (свой женский голос)

## Цель

Нормальный **женский** голос для Cursor TTS. Piper-Ирина не зашла. Рабочее имя: **micro wife** — текстовый voice design через Qwen, не «ещё один onnx».

## Железо

i5-12450H / 16 GB / **RTX 3050 4 GB** → **Qwen3-TTS-12Hz-0.6B-CustomVoice** + speaker Serena + instruct.  
(VoiceDesign 1.7B на 4GB часто OOM — не дефолт.)

## Не в scope

- Ломать Edge / Silero / Piper  
- Neuro-агент (IDEA-001)  
- Клон с чужих аудиокниг / чтецов  

## Сделано (2026-08-14)

- [`Cursor_TTS/micro_wife/`](../../Cursor_TTS/micro_wife/) — `speak_qwen.py`, `prototype_micro_wife.py`, 4 design-пресета  
- Активный design: `designs/02_soft_high_female.txt` (мягкий высокий / книжный)  
- `engine: "qwen"` в демоне + пункт **Micro wife (Qwen)** в панели  
- pause / stop / очередь как у Piper; короткие куски (~220 символов)

## Design-пресеты

1. яркий мужской (театр)  
2. **мягкий высокий — micro wife**  
3. тёмный мужской (саспенс)  
4. баритон-чтец  

## Установка

См. [`Cursor_TTS/micro_wife/README.md`](../../Cursor_TTS/micro_wife/README.md).

## Готово когда

В панели выбирается Micro wife; русская фраза звучит «своей» женской, не как Piper-Ирина; Edge/Silero/Piper живы.
