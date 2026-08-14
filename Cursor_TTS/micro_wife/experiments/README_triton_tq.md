# Эксперимент: Triton / TurboQuant (изолированно)

**Не подключено к панели/демону.** Прод-путь Qwen не менялся.

## Что это вообще

| Термин | Простыми словами |
|--------|------------------|
| **Triton** | Язык кастомных GPU-ядер. Склеивает несколько мелких операций в одну, меньше гонок в память. |
| **TurboQuant (TQ)** | Сжимает KV-кэш внимания до INT4/INT3 — обычно экономит VRAM; на больших моделях иногда и ускоряет. |
| **Hybrid** | `faster-qwen3-tts` (CUDA Graphs) + патч Triton-ядрами. |
| **Hybrid+TQ** | Hybrid + сжатый KV-кэш. |

Авторы `qwen3-tts-triton` тестировали на **RTX 5090 / 8GB+ / WSL2 / модель 1.7B**. У нас: **3050 Laptop 4GB / Windows / 0.6B**.

## Как гонять

```powershell
# venv уже есть: C:\Users\Home\.venvs\qwen_tq
C:\Users\Home\.venvs\qwen_tq\Scripts\python.exe `
  Cursor_TTS\micro_wife\experiments\benchmark_triton_tq.py
```

## Результат на RTX 3050 Laptop (одна и та же фраза ~6–8 с речи)

| Режим | gen | RTF | вердикт |
|-------|-----|-----|---------|
| **baseline faster (прод)** | **12.4 с** | **1.94** | победитель |
| hybrid (Triton) | 25.5 с | 3.79 | ~2× медленнее |
| hybrid+TQ | 28.4 с | 3.59 | ещё хуже |

Вывод: на этой карте **не вшивать** в прод. Оверхед Triton/TQ съедает выигрыш (и/или ядра плохо дружат с уже захваченными CUDA graphs на Ampere 4GB).

WAV: `experiments/out/tq_*.wav`
