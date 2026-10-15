' Launch HH AutoApply UI without a visible console (как YouTube_Translator).
' Код Python меняешь — пересобирать ничего не надо. Ярлык → этот .vbs.
Option Explicit

Dim sh, fso, dir, wrapper, pythonw, python, logPath, probePath, probeRc, errText, guiExe, winStyle, msgTitle

msgTitle = "HH AutoApply"

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
If LCase(fso.GetFileName(dir)) = "launch" Then
  dir = fso.GetParentFolderName(dir)
End If

wrapper = dir & "\launch_gui.py"
logPath = dir & "\_launch_error.log"
probePath = dir & "\_launch_probe.log"

If Not fso.FileExists(wrapper) Then
  MsgBox "Missing launch_gui.py:" & vbCrLf & wrapper, vbCritical, msgTitle
  WScript.Quit 1
End If

If Not fso.FolderExists(dir & "\hh_auto") Then
  MsgBox "hh_auto package not found:" & vbCrLf & dir & "\hh_auto", vbCritical, msgTitle
  WScript.Quit 1
End If

sh.CurrentDirectory = dir
pythonw = FindExe("pythonw.exe")
python = FindExe("python.exe")

If python = "" And pythonw = "" Then
  MsgBox "pythonw/python not found in PATH." & vbCrLf & _
         "Install Python or run: python -m hh_auto ui", _
         vbCritical, msgTitle
  WScript.Quit 1
End If

' Быстрый probe: customtkinter (UI dep)
If python <> "" Then
  On Error Resume Next
  If fso.FileExists(probePath) Then fso.DeleteFile probePath, True
  On Error GoTo 0
  probeRc = sh.Run( _
    "cmd /c """"" & python & """ -c ""import customtkinter"" 1>""" & probePath & """ 2>&1""", _
    0, True)
  If probeRc <> 0 Then
    errText = ReadLogTail(probePath, 1200)
    If errText = "" Then errText = "(no text in _launch_probe.log, code " & probeRc & ")"
    MsgBox "Failed to start HH AutoApply." & vbCrLf & vbCrLf & _
           errText & vbCrLf & vbCrLf & _
           "Try: pip install -r requirements.txt" & vbCrLf & _
           "Full log: " & probePath, _
           vbCritical, msgTitle
    WScript.Quit 1
  End If
End If

If pythonw <> "" Then
  guiExe = pythonw
  winStyle = 1
  AppendLaunchLine logPath, "launch: vbs pythonw (" & guiExe & ")"
Else
  guiExe = python
  winStyle = 1
  AppendLaunchLine logPath, "launch: vbs python (" & guiExe & ")"
End If

AppendLaunchLine logPath, "vbs -> " & guiExe & " " & Chr(34) & wrapper & Chr(34)
sh.Run Chr(34) & guiExe & Chr(34) & " " & Chr(34) & wrapper & Chr(34), winStyle, False

Function StampNow()
  Dim d
  d = Now
  StampNow = Year(d) & "-" & Right("0" & Month(d), 2) & "-" & Right("0" & Day(d), 2) & " " & _
             Right("0" & Hour(d), 2) & ":" & Right("0" & Minute(d), 2) & ":" & Right("0" & Second(d), 2)
End Function

Sub AppendLaunchLine(path, msg)
  Dim ts
  On Error Resume Next
  Set ts = fso.OpenTextFile(path, 8, True)
  If Err.Number = 0 Then
    ts.WriteLine "[" & StampNow() & "] " & msg
    ts.Close
  End If
  On Error GoTo 0
End Sub

Function ReadLogTail(path, maxChars)
  Dim ts, all
  ReadLogTail = ""
  If Not fso.FileExists(path) Then Exit Function
  On Error Resume Next
  Set ts = fso.OpenTextFile(path, 1, False, 0)
  If Err.Number <> 0 Then
    On Error GoTo 0
    Exit Function
  End If
  all = ts.ReadAll
  ts.Close
  On Error GoTo 0
  If Len(all) > maxChars Then
    ReadLogTail = Right(all, maxChars)
  Else
    ReadLogTail = all
  End If
End Function

Function FindExe(name)
  Dim e, p, parts, i
  FindExe = ""
  On Error Resume Next
  e = sh.ExpandEnvironmentStrings("%PATH%")
  On Error GoTo 0
  parts = Split(e, ";")
  For i = LBound(parts) To UBound(parts)
    p = Trim(parts(i))
    If p <> "" Then
      If Right(p, 1) <> "\" Then p = p & "\"
      If fso.FileExists(p & name) Then
        FindExe = p & name
        Exit Function
      End If
    End If
  Next
  p = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python")
  If fso.FolderExists(p) Then
    Dim folder, subf, hit
    Set folder = fso.GetFolder(p)
    For Each subf In folder.SubFolders
      hit = subf.Path & "\" & name
      If fso.FileExists(hit) Then
        FindExe = hit
        Exit Function
      End If
    Next
  End If
End Function
