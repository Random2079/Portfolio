#NoEnv
#SingleInstance Force
; Считаем координаты ровно так же, как в основном макросе
CoordMode, Mouse, Client

SetTimer, WatchMouse, 50
return

WatchMouse:
    MouseGetPos, x, y
    ToolTip, X: %x% `nY: %y%
return

; Нажми вторую боковую кнопку мыши, чтобы выключить сканер
XButton2:: ExitApp