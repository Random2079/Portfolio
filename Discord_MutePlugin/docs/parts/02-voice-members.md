# 02 — Voice members (слой A)

**Код:** `src/voiceMuteSlots/voiceMembers.ts`, `src/voiceMuteSlots/index.ts`  
**Навигация:** [INDEX](INDEX.md) · [TZ](../TZ.md)

## Вход / выход

**Вход:** Discord stores (текущий клиент в voice).

**Выход:** `VoiceSnapshot`:

```ts
{
  inVoice: true,
  lobby: { guildId, guildName, channelId, channelName, label },
  me: { slot, userId, name, isMe: true },
  others: [{ slot, userId, name, isMe: false }, ...],
  slots: [ /* me + others, 1-based slot */ ]
}
```

## Finder'ы (Equicord / Vencord webpack)

| Store / API | Как получить | Зачем |
|-------------|--------------|-------|
| **`SortedVoiceStateStore`** | `findStoreLazy("SortedVoiceStateStore")` | **порядок sidebar** (слоты) |
| `VoiceStateStore` | `@webpack/common` | мой channelId, fallback list |
| `UserStore` | `@webpack/common` | me, display names |
| `ChannelStore` | `@webpack/common` | channel name / object for Sorted* |
| `GuildStore` | `@webpack/common` | guild name |
| `GuildMemberStore` | `@webpack/common` | server nick |

### Методы

- `VoiceStateStore.getVoiceStateForUser(meId)?.channelId` — мой канал
- `SortedVoiceStateStore.getVoiceStatesForChannel(channel)` — **упорядоченный** список sidebar
- `SortedVoiceStateStore.getVoiceStatesForChannelAlt(channelId, guildId)` — то же по ids
- `VoiceStateStore.getVoiceStatesForChannel(channelId)` — Record (без порядка; только fallback)
- `UserStore.getCurrentUser()` — me
- `UserStore.getUser(userId)` / `GuildMemberStore.getNick` — имя

## Порядок слотов (важно)

Слоты = **визуальный порядок левого guild sidebar** под голосовым каналом (сверху вниз, включая себя).

Источник правды Discord: **`SortedVoiceStateStore`** (не сырой `VoiceStateStore`).

Плагин вызывает `getVoiceStatesForChannel(channel)` / `getVoiceStatesForChannelAlt(channelId, guildId)` — уже отсортированный массив.  
Fallback (если store не найден): тот же компаратор, что в Discord 1.0.9253:

```text
comparator = (selfStream ? "\0" : "\x01") + name.toLowerCase() + "\0" + userId
```

Где `name` = guild nick → globalName → username.

| Влияет на sidebar | Не влияет |
|-------------------|-----------|
| Go Live (`selfStream`) — выше всех | **Камера (`selfVideo`)** — только call/RTC grid |
| lowercase display name | Speaking / local-mute |
| `userId` tie-break | Join time |

**Не** путать с сортировкой сетки звонка (там есть video/stream tiers) — для слотов только guild channel list.

Число вроде **«21»** на Lounge — это **имя голосового канала**, не секция алфавита. Список под каналом плоский.

`Object.values(VoiceStateStore…)` без sort ≠ sidebar.  
Ошибка с `selfVideo` как отдельным тиром + `localeCompare` давала неверный индекс (Brooklyn визуально #1, слот #3).

## События

- `flux.VOICE_STATE_UPDATES` — join/leave/mute flags
- Debounce toast 2s, лог только при изменении snapshot

## Проверка

1. В voice с 2+ людьми
2. `/voice-slots` — toast: `#1 …, #2 …` **сверху вниз как в sidebar** (включая me)
3. Console: `[VoiceMuteSlots] lobby=… source=SortedVoiceStateStore slots=[#1 "…" key=\x01…, …]`
4. Кто-то зашёл/вышел / включил LIVE — новый toast, слоты пересчитались
5. Регресс: камера у кого-то **не** должна двигать слоты; LIVE — да (стримеры сверху)
