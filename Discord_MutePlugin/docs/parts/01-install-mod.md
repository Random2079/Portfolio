# 01 — Установка Equicord + userplugin

**Код:** `launch/install-to-equicord.ps1`  
**Навигация:** [INDEX](INDEX.md) · [TZ](../TZ.md)

## Статус машины (2026-08-25, сделано агентом)

| Что | Путь / факт | Статус |
|-----|-------------|--------|
| Node LTS | v24.19.0 (winget) | ✅ |
| pnpm | 11.23.0 | ✅ |
| Клон Equicord | `C:\Users\Home\dev\Equicord` | ✅ |
| Userplugin | `...\src\userplugins\voiceMuteSlots\` | ✅ |
| Build | `...\dist\desktop\` (VoiceMuteSlots внутри) | ✅ |
| Inject | Discord Stable → `require(...\Equicord\dist\desktop)` | ✅ |
| Settings | VoiceMuteSlots **enabled** | ✅ |
| Equilotl.exe | `C:\Users\Home\Downloads\Equilotl.exe` | ✅ (legacy) |

## Проверка слоя A (когда свободен)

1. Запустить Discord  
2. В voice: `/voice-slots`  
3. Toast + Console `[VoiceMuteSlots] lobby=…`

См. также корневой `READY_WHEN_FREE.md`.

## Обновление плагина после правок в Discord_MutePlugin

```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
$env:EQUICORD_SRC = 'C:\Users\Home\dev\Equicord'
cd C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_MutePlugin
.\launch\install-to-equicord.ps1
cd $env:EQUICORD_SRC
pnpm build
# non-interactive inject:
$env:EQUICORD_USER_DATA_DIR = $env:EQUICORD_SRC
$env:EQUICORD_DIRECTORY = Join-Path $env:EQUICORD_SRC 'dist\desktop'
$env:EQUICORD_DEV_INSTALL = '1'
& .\dist\Installer\EquilotlCli.exe -install -branch stable
```

Discord лучше закрыть перед inject.
