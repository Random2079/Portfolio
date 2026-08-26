# Discord_MutePlugin (IDEA-005)

Local mute по **слоту N** в текущем voice-канале через **Equicord** (внутренние Discord stores). Без OCR, без кликов, без бота.

## Структура

```
Discord_MutePlugin/
├── src/voiceMuteSlots/   ← Equicord userplugin (копировать в Equicord/src/userplugins/)
├── docs/                 ← ТЗ и parts
└── launch/               ← скрипт копирования в Equicord source
```

## Быстрый старт (Equicord уже стоит)

1. Клон Equicord + сборка: `docs/parts/01-install-mod.md`
2. Скопировать плагин:
   ```powershell
   $env:EQUICORD_SRC = "C:\path\to\Equicord"
   .\launch\install-to-equicord.ps1
   cd $env:EQUICORD_SRC; pnpm build; pnpm inject
   ```
3. В Discord: Settings → Equicord → Plugins → **VoiceMuteSlots** → Enable
4. Зайти в voice → `/voice-slots` или смотреть консоль (Ctrl+Shift+I)

## Слои

| Слой | Статус | Что делает |
|------|--------|------------|
| A | 🟡 | lobby + me + others[], лог/toast |
| B | ⬜ | local mute slot N |
| C | ⬜ | hotkey Shift+1..6 |

Legacy OCR: `_archive/Discord_VoiceMute/` — не трогать.
