@echo off
cd /d "%~dp0"
set "PYW=%LocalAppData%\Programs\Python\Python313\pythonw.exe"
if not exist "%PYW%" set "PYW=C:\Users\Home\AppData\Local\Programs\Python\Python313\pythonw.exe"

REM Start hotkeys with AutoHotkey v1 (modern install is under v1.1.*)
set "AHK="
if exist "C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU64.exe" set "AHK=C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU64.exe"
if not defined AHK if exist "C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU32.exe" set "AHK=C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU32.exe"
if not defined AHK if exist "C:\Program Files\AutoHotkey\AutoHotkeyU64.exe" set "AHK=C:\Program Files\AutoHotkey\AutoHotkeyU64.exe"
if not defined AHK if exist "C:\Program Files\AutoHotkey\AutoHotkey.exe" set "AHK=C:\Program Files\AutoHotkey\AutoHotkey.exe"
if not defined AHK if exist "C:\Program Files\AutoHotkey\UX\AutoHotkeyUX.exe" set "AHK=C:\Program Files\AutoHotkey\UX\AutoHotkeyUX.exe"

if exist "%~dp0hotkey_tts.ahk" (
  if defined AHK (
    start "" "%AHK%" "%~dp0hotkey_tts.ahk"
  ) else (
    start "" "%~dp0hotkey_tts.ahk"
  )
)

if not exist "%PYW%" (
  echo Python не найден. Запускаю с python и покажу ошибку...
  python "%~dp0TTS_Panel.py"
  pause
  exit /b 1
)

start "" "%PYW%" "%~dp0TTS_Panel.py"
