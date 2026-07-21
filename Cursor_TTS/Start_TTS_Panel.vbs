Option Explicit

Dim shell, fso, folder, panel, pythonw, ahkScript, ahkExe, cmd

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
panel = folder & "\TTS_Panel.py"
ahkScript = folder & "\hotkey_tts.ahk"
pythonw = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python313\pythonw.exe"

If Not fso.FileExists(pythonw) Then
  pythonw = "C:\Users\Home\AppData\Local\Programs\Python\Python313\pythonw.exe"
End If

If Not fso.FileExists(panel) Then
  MsgBox "Не найден файл:" & vbCrLf & panel, vbCritical, "Cursor TTS"
  WScript.Quit 1
End If

If Not fso.FileExists(pythonw) Then
  MsgBox "Не найден pythonw.exe." & vbCrLf & vbCrLf & _
    "Установи Python или запусти из папки Cursor_TTS:" & vbCrLf & _
    "python TTS_Panel.py", vbCritical, "Cursor TTS"
  WScript.Quit 1
End If

' Поднять хоткеи: явный v1 exe (современный AHK лежит в v1.1.*/v2/, не в корне)
If fso.FileExists(ahkScript) Then
  ahkExe = FindAhkV1()
  If ahkExe <> "" Then
    shell.Run """" & ahkExe & """ """ & ahkScript & """", 0, False
  Else
    ' UX launcher + #Requires AutoHotkey v1.1 в скрипте
    shell.Run """" & ahkScript & """", 0, False
  End If
End If

shell.CurrentDirectory = folder
cmd = """" & pythonw & """ """ & panel & """"
shell.Run cmd, 0, False

Function FindAhkV1()
  Dim candidates(6), i
  candidates(0) = "C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU64.exe"
  candidates(1) = "C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU32.exe"
  candidates(2) = "C:\Program Files\AutoHotkey\AutoHotkeyU64.exe"
  candidates(3) = "C:\Program Files\AutoHotkey\AutoHotkey.exe"
  candidates(4) = "C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe"
  candidates(5) = "C:\Program Files\AutoHotkey\UX\AutoHotkeyUX.exe"
  For i = 0 To 5
    If fso.FileExists(candidates(i)) Then
      FindAhkV1 = candidates(i)
      Exit Function
    End If
  Next
  FindAhkV1 = ""
End Function
