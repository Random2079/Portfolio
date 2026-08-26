# 04 — Commands / UX (A + B + C голос)

**Код:** `src/voiceMuteSlots/index.ts`, `parseCommand.ts`, `voiceListen.ts`  
**Навигация:** [INDEX](INDEX.md) · [TZ](../TZ.md)

## Слой A

| Command | Описание |
|---------|----------|
| `/voice-slots` | lobby, me, others с номерами |

## Слой B

| Command | Описание |
|---------|----------|
| `/mute-slot slot:N` | Local mute слота N |
| `/parse-voice text:…` | Тест парсера без микрофона |

## Слой C — голос офлайн (Vosk)

Google Web Speech **не используем** (нужен интернет / ломается в Discord).

1. Запусти `launch\Start-VoiceStt.ps1` (daemon `:39281`)
2. Зажми **Shift+K**
3. Скажи: `заткни 3` / `замуть семь` / `завали 5`
4. Отпусти Shift+K

Красный баннер сверху = слушаю. `/stt-check` = жив ли daemon.

## Проверка

1. `/parse-voice text:заткни три` → mute #3  
2. В voice: Shift+K + «замуть 7» → local mute #7  
3. Console: `[VoiceMuteSlots] STT: … → mute #7`
