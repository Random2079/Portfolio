' ������ Subtitle Ripper Pro ��� ������� ���� �������.
' �����: ���� ���� ��� launch\run.vbs
' ��� ������� import/startup: MsgBox + ������ traceback � _launch_error.log
Option Explicit

Dim sh, fso, dir, app, pythonw, python, logPath, probeRc, errText

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
' ���� ����� � launch\ � ������ ������� �� ������� ����
If LCase(fso.GetFileName(dir)) = "launch" Then
  dir = fso.GetParentFolderName(dir)
End If

app = dir & "\Subtitle_App.py"
logPath = dir & "\_launch_error.log"

If Not fso.FileExists(app) Then
  MsgBox "�� ������ Subtitle_App.py:" & vbCrLf & app, vbCritical, "Subtitle Ripper Pro"
  WScript.Quit 1
End If

sh.CurrentDirectory = dir
pythonw = FindExe("pythonw.exe")
python = FindExe("python.exe")

If python = "" And pythonw = "" Then
  MsgBox "�� ������ pythonw/python � PATH." & vbCrLf & _
         "�������� Python ��� �������: python Subtitle_App.py", _
         vbCritical, "Subtitle Ripper Pro"
  WScript.Quit 1
End If

' ���������� �������� ������� (������� ������ ������ ������ pythonw)
If python <> "" Then
  On Error Resume Next
  If fso.FileExists(logPath) Then fso.DeleteFile logPath, True
  On Error GoTo 0
  probeRc = sh.Run( _
    "cmd /c """"" & python & """ -c ""import Subtitle_App"" 1>""" & logPath & """ 2>&1""", _
    0, True)
  If probeRc <> 0 Then
    errText = ReadLogTail(logPath, 1200)
    If errText = "" Then errText = "(��� ������ � _launch_error.log, ��� " & probeRc & ")"
    MsgBox "�� ������� ��������� Subtitle Ripper Pro." & vbCrLf & vbCrLf & _
           errText & vbCrLf & vbCrLf & _
           "������ ���: " & logPath, _
           vbCritical, "Subtitle Ripper Pro"
    WScript.Quit 1
  End If
End If

' GUI: pythonw ��� �������; stderr > _launch_error.log �� ������ �������� �����
If pythonw <> "" Then
  sh.Run "cmd /c """"" & pythonw & """ """ & app & """ 1>>""" & logPath & """ 2>&1""", 0, False
Else
  sh.Run "cmd /c """"" & python & """ """ & app & """ 1>>""" & logPath & """ 2>&1""", 1, False
End If

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
  ' ������ ���� ����������� Python
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