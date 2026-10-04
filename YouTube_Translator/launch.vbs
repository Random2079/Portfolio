' Launch Subtitle Ripper Pro without a visible console.
' Same entry as launch\run.vbs (delegates here).
' Import/startup probe: MsgBox + traceback in _launch_error.log
' GUI: pythonw launch_gui.py (stdio teed to _launch_error.log; no cmd /c)
Option Explicit

Dim sh, fso, dir, app, wrapper, pythonw, python, logPath, probeRc, errText, guiExe, winStyle

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
' If this script lives under launch\, step up to project root
If LCase(fso.GetFileName(dir)) = "launch" Then
  dir = fso.GetParentFolderName(dir)
End If

app = dir & "\Subtitle_App.py"
wrapper = dir & "\launch_gui.py"
logPath = dir & "\_launch_error.log"

If Not fso.FileExists(app) Then
  MsgBox "Subtitle_App.py not found:" & vbCrLf & app, vbCritical, "Subtitle Ripper Pro"
  WScript.Quit 1
End If

If Not fso.FileExists(wrapper) Then
  MsgBox "Missing launch_gui.py:" & vbCrLf & wrapper, vbCritical, "Subtitle Ripper Pro"
  WScript.Quit 1
End If

sh.CurrentDirectory = dir
pythonw = FindExe("pythonw.exe")
python = FindExe("python.exe")

If python = "" And pythonw = "" Then
  MsgBox "pythonw/python not found in PATH." & vbCrLf & _
         "Install Python or run: python Subtitle_App.py", _
         vbCritical, "Subtitle Ripper Pro"
  WScript.Quit 1
End If

' Fail-fast import probe (needs console python + redirect; hidden window)
If python <> "" Then
  On Error Resume Next
  If fso.FileExists(logPath) Then fso.DeleteFile logPath, True
  On Error GoTo 0
  probeRc = sh.Run( _
    "cmd /c """"" & python & """ -c ""import Subtitle_App"" 1>""" & logPath & """ 2>&1""", _
    0, True)
  If probeRc <> 0 Then
    errText = ReadLogTail(logPath, 1200)
    If errText = "" Then errText = "(no text in _launch_error.log, code " & probeRc & ")"
    MsgBox "Failed to start Subtitle Ripper Pro." & vbCrLf & vbCrLf & _
           errText & vbCrLf & vbCrLf & _
           "Full log: " & logPath, _
           vbCritical, "Subtitle Ripper Pro"
    WScript.Quit 1
  End If
End If

' GUI: pythonw on launch_gui.py - no cmd, no console flash; crashes go to log
If pythonw <> "" Then
  guiExe = pythonw
  winStyle = 0
Else
  guiExe = python
  winStyle = 1
End If

If pythonw <> "" Then
  AppendLaunchLine logPath, "launch: vbs pythonw (" & guiExe & ")"
Else
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
  ' Typical per-user Python install
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
