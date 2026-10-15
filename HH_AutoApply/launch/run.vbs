' То же, что ../launch.vbs — для структуры IDEA-020 (папка launch/)
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run "wscript.exe //nologo """ & _
  CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & _
  "\..\launch.vbs""", 0, False
