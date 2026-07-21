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
pidFile := A_ScriptDir . "\tts_speech.pid"
selFile := A_Temp . "\cursor_tts_selection.txt"
dbgLog := A_ScriptDir . "\..\debug-45ab72.log"

; #region agent log
FileAppend, % "AHK_START v1 python=" pythonExe "`n", %dbgLog%
; #endregion

; Ctrl+Shift — удобнее Win+Alt, реже конфликтует чем Ctrl+Alt
; Ctrl+Shift+T — toggle AUTO
; Ctrl+Shift+X — STOP
; Ctrl+Shift+S — speak SELECTED text

^+t::
    ; #region agent log
    FileAppend, AHK_HOTKEY Ctrl+Shift+T`n, %dbgLog%
    ; #endregion
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
    ; #region agent log
    FileAppend, AHK_HOTKEY Ctrl+Shift+X`n, %dbgLog%
    ; #endregion
    Gosub, StopSpeech
    ToolTip, TTS: STOP, 10, 10
    SetTimer, RemoveTip, -1500
return

^+s::
    ; #region agent log
    FileAppend, AHK_HOTKEY Ctrl+Shift+S`n, %dbgLog%
    ; #endregion
    Gosub, StopSpeech

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

    ToolTip, TTS: speaking selection..., 10, 10
    SetTimer, RemoveTip, -1500
    Run, "%pythonExe%" "%A_ScriptDir%\speak_edge.py" "%selFile%", , Hide, ttsPID
    if (ttsPID) {
        FileDelete, %pidFile%
        FileAppend, %ttsPID%, %pidFile%
    }
return

StopSpeech:
    ; #region agent log
    FileAppend, AHK_STOPSPEECH`n, %dbgLog%
    ; #endregion
    if (ttsPID) {
        Process, Close, %ttsPID%
        ttsPID := 0
    }
    RunWait, "%pythonExe%" "%A_ScriptDir%\speak_edge.py" --stop, , Hide
    ; #region agent log
    FileAppend, % "AHK_STOP_DONE err=" ErrorLevel "`n", %dbgLog%
    ; #endregion
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
