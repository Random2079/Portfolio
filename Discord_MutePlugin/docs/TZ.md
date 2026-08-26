# TZ — Discord_MutePlugin (IDEA-005)

## Цель

Замутить **N-го человека** в текущем voice-канале **локально** (себе не слышать), через плагин Equicord/Vencord — без OCR, без pyautogui, без бота.

## MVP / слои

| Слой | Статус | Описание |
|------|--------|----------|
| 0 | ✅ | Equicord установлен |
| A | ✅ | Voice stores → `lobby` + `me` + `others[]`, лог + toast |
| B | ✅ | `VoiceActions.toggleLocalMute` по `/mute-slot` |
| C | 🟡 | Голос: Shift+K → STT daemon → parse → mute. **Слоты/mute ✅; распознавалка ❌.** Выбор движка — `docs/TZ-STT.md` |

## Термины

- **lobby** — текущий voice-канал: guild + channel name (как «14 / Lounge» в legacy, но из stores)
- **me** — текущий пользователь в этом канале
- **others[]** — остальные в канале, **без me**
- **slot** — 1-based индекс в списке **всех** в канале (me + others) в порядке **левого Discord sidebar** (`SortedVoiceStateStore`: LIVE/stream → lowercase nick → userId; камера **не** двигает список); mute self → «это я», без mute
- **mute** — только **local mute**, не server-mute

## Не делаем

- OCR / PrintWindow / клики по экрану
- Discord-бот
- Server-mute / deafen других
- Правки `_archive/Discord_VoiceMute/` без явной просьбы
- Exe / Python-tray (это legacy)

## Готово когда

- [x] Equicord стоит
- [ ] В voice: `/voice-slots` показывает lobby, me, others с номерами слотов
- [ ] При join/leave в канале — toast + строка в консоли
- [ ] Слот N → local mute нужного userId (не me)
- [ ] После обновления Discord — finder'ы задокументированы в parts

## Проверка (слой A)

1. Enable plugin **VoiceMuteSlots**
2. Зайти в guild voice (например Lounge)
3. `/voice-slots` → toast вида `Lounge | me: #2 Ищу… | others: #1 Alice, #3 Bob`
4. DevTools console → `[VoiceMuteSlots] lobby=… me=… others=[…]`
5. Другой человек join/leave → новый toast (не чаще 1 раз / 2 сек)

## Parts ↔ код

| Part | Файлы |
|------|--------|
| 01-install-mod | `launch/install-to-equicord.ps1` |
| 02-voice-members | `src/voiceMuteSlots/voiceMembers.ts`, `index.ts` (flux A) |
| 03-local-mute | `src/voiceMuteSlots/localMute.ts`, `index.ts` |
| 04-commands | `src/voiceMuteSlots/index.ts`, `parseCommand.ts` |
| **STT выбор** | **`docs/TZ-STT.md`** → код `stt/`, `voiceListen.ts` |

## Мод

**Equicord** (вариант 1). Userplugin → `src/userplugins/voiceMuteSlots/`, rebuild обязателен.
