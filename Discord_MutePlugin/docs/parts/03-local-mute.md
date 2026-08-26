# 03 — Local mute (слой B)

**Код:** `src/voiceMuteSlots/localMute.ts`, `src/voiceMuteSlots/index.ts`  
**Навигация:** [INDEX](INDEX.md) · [TZ](../TZ.md)

## Статус: ✅

## Finder'ы

| API | Источник | Назначение |
|-----|----------|------------|
| `VoiceActions.toggleLocalMute(userId)` | `@webpack/common` (`findByPropsLazy("toggleSelfMute")`) | local mute |
| `MediaEngineStore.isLocalMute(userId)` | `@webpack/common` | уже замьючен? |
| `GuildMemberStore.getNick(guildId, userId)` | `@webpack/common` | ник как в sidebar |

**Не использовать:** `GuildActions.setServerMute` — server-mute.

## Логика

1. `/mute-slot slot:N` → `getVoiceSnapshot()` → слот N
2. `isMe` → toast «Это я»
3. `isLocalMute` → «уже замьючен», без toggle
4. иначе `VoiceActions.toggleLocalMute(userId)`

## Проверка

1. `/voice-slots` — Stp1 = #7 (пример)
2. `/mute-slot slot:7` → toast `Local mute: #7 Stp1`
3. У тебя Stp1 не слышен; у других слышен (server mute не трогали)
4. Повтор `/mute-slot slot:7` → «уже локально замьючен»
5. `/mute-slot slot:8` (ты) → «Это я»

Unmute пока вручную в UI Discord или позже `/unmute-slot`.
