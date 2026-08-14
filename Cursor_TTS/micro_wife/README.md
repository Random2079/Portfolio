# Micro wife (IDEA-013) — Qwen3-TTS

Свой женский (и другие) голоса через **текстовый design**, не через чужие mp3.

## Установка (один раз)

```powershell
cd Cursor_TTS
pip install -U qwen-tts soundfile
pip install -U faster-qwen3-tts
# GPU (RTX 3050): torch+torchaudio с одной версией CUDA
pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

Важно: `torchaudio` должен совпадать с `torch` (например оба `2.6.0+cu124`).
Основной backend — `faster-qwen3-tts`: **BF16 + SDPA + CUDA Graphs**. На RTX 3050
4 GB он занимает около 3.15 GB VRAM. Официальный `qwen_tts` FP32 остаётся fallback.

Проверка:

```powershell
cd micro_wife
python prototype_micro_wife.py
```

Первый запуск качает `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` с Hugging Face (~несколько GB).

## Как работает

- Модель: **0.6B CustomVoice** (влезает в 4 GB VRAM).
- Базовый speaker: **Serena** (тёплый женский).
- Важно: 0.6B официально **не поддерживает instruct** — design-файлы здесь служат
  именованными пресетами выбора встроенного speaker. Полноценный VoiceDesign/instruct
  требует модели 1.7B и примерно 6–8 GB VRAM, поэтому на этой RTX 3050 не помещается.
- Замер RTX 3050 Laptop: тёплая фраза 42 символа — генерация ~7.4 с вместо ~87 с
  на старом backend; CUDA-graph warmup выполняется при старте панели.

Движок в панели: **Micro wife (Qwen)** (премиум) рядом с **Kokoro-ru** (быстрее).
В списке голосов Qwen — design-пресеты.

| Пресет | Файл |
|--------|------|
| 2 · micro wife (выбор) | `designs/02_soft_high_female.txt` |
| 1 · яркий мужской | `designs/01_bright_male_theater.txt` |
| 3 · тёмный саспенс | `designs/03_dark_male_suspense.txt` |
| 4 · баритон | `designs/04_neutral_baritone.txt` |

Активный текст также копируется в `voice_design.txt`.

## Конфиг (`tts_config.json`)

```json
"engine": "qwen",
"qwen_model": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
"qwen_speaker": "Serena",
"micro_wife_design_file": "micro_wife/designs/02_soft_high_female.txt"
```

Очередь / pause / stop — те же, что у Piper (демон).

## Не класть сюда

Чужие аудиокниги как сэмпл для клона. Только свои wav в `samples/` (если позже включим Base clone) или текстовые design.
