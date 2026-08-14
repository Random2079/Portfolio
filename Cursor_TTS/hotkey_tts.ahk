#Requires AutoHotkey v1.1
#NoEnv
#SingleInstance Force
SetWorkingDir %A_ScriptDir%

; Prefer full python path so AHK finds it even with a thin PATH.
EnvGet, localAppData, LOCALAPPDATA
pythonExe := localAppData . "\Programs\Python\Python313\python.exe"
if (!FileExist(pythonExe))
    pythonExe := "C:\Users\Home\AppData\Local\Programs\Python\Python313\python.exe"
if (!FileExist(pythonExe))
    pythonExe := "python"

; AHK ToolTip on Windows often breaks Cyrillic — keep tip text ASCII.

global ttsPID := 0
global pythonExe
offFlag := A_ScriptDir . "\TTS_OFF"
pauseFlag := A_ScriptDir . "\TTS_PAUSED"
pidFile := A_ScriptDir . "\tts_speech.pid"
selFile := A_Temp . "\cursor_tts_selection.txt"

; Ctrl+Shift — удобнее Win+Alt, реже конфликтует чем Ctrl+Alt
; Ctrl+Shift+T — toggle AUTO
; Ctrl+Shift+X — STOP (clear queue)
; Ctrl+Shift+P — PAUSE / RESUME
; Ctrl+Shift+S — speak SELECTED text

^+t::
    if (FileExist(offFlag)) {
        FileDelete, %offFlag%
        ToolTip, TTS AUTO: ON, 10, 10
    } else {
        FileAppend,, %offFlag%
        Gosub, StopSpeech
        ToolTip, TTS AUTO: OFF, 10, 10
    }
    SetTimer, RemoveTip, -2000
return

^+x::
    Gosub, StopSpeech
    ToolTip, TTS: STOP, 10, 10
    SetTimer, RemoveTip, -1500
return

^+p::
    RunWait, "%pythonExe%" "%A_ScriptDir%\speak_edge.py" --pause-toggle, , Hide
    ; Файл TTS_PAUSED пишет демон: есть = пауза, нет = играет
    if (FileExist(pauseFlag)) {
        ToolTip, TTS: PAUSED  (Ctrl+Shift+P = resume), 10, 10
        SetTimer, RemoveTip, -5000
    } else {
        ToolTip, TTS: PLAYING, 10, 10
        SetTimer, RemoveTip, -2500
    }
return

^+s::
    ; Сначала копируем выделение — Stop до ^c часто срывает фокус в Cursor
    clipSaved := ClipboardAll
    Clipboard :=
    SendInput, ^c
    ClipWait, 1
    if (ErrorLevel) {
        Clipboard := clipSaved
        ToolTip, TTS: select text first, 10, 10
        SetTimer, RemoveTip, -2000
        return
    }

    RunWait, powershell -NoProfile -Command "Get-Clipboard -Raw | Set-Content -LiteralPath '%selFile%' -Encoding UTF8", , Hide
    Clipboard := clipSaved

    Gosub, StopSpeech

    ToolTip, TTS: speaking selection..., 10, 10
    SetTimer, RemoveTip, -1500
    Run, "%pythonExe%" "%A_ScriptDir%\speak_edge.py" "%selFile%", , Hide, ttsPID
    if (ttsPID) {
        FileDelete, %pidFile%
        FileAppend, %ttsPID%, %pidFile%
    }
return

StopSpeech:
    if (ttsPID) {
        Process, Close, %ttsPID%
        ttsPID := 0
    }
    RunWait, "%pythonExe%" "%A_ScriptDir%\speak_edge.py" --stop, , Hide
    if (FileExist(pidFile)) {
        FileRead, speechPID, %pidFile%
        speechPID := Trim(speechPID)
        if (speechPID)
            RunWait, %ComSpec% /c taskkill /F /T /PID %speechPID% >nul 2>&1, , Hide
        FileDelete, %pidFile%
    }
return

RemoveTip:
    ToolTip
return
