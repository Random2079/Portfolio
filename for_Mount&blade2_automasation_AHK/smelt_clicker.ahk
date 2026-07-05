#NoEnv
#SingleInstance Force
SetWorkingDir %A_ScriptDir%

isClicking := false

XButton1::
    isClicking := !isClicking
    if (isClicking) {
        ToolTip, AUTO CLICK ON, 10, 10
        SetTimer, DoClick, 10
    } else {
        ToolTip, AUTO CLICK OFF, 10, 10
        SetTimer, DoClick, Off
    }
    SetTimer, RemoveToolTip, -1000
return

DoClick:
    Click
return

XButton2::
    ToolTip
    ExitApp
return

RemoveToolTip:
    ToolTip
return