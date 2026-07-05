#NoEnv
#SingleInstance Force
SetWorkingDir %A_ScriptDir%

; Кликаем строго внутри окна игры
CoordMode, Mouse, Client

isForging := false

; --- СТАРТ / ПАУЗА (Первая боковая кнопка мыши) ---
XButton1::
    isForging := !isForging
    if (isForging) {
        ToolTip, 🔨 КРАФТ ЗАПУЩЕН, 10, 10
        SetTimer, ForgeLoop, 10 ; Включаем бесконечный цикл
    } else {
        ToolTip, 🛑 КРАФТ НА ПАУЗЕ, 10, 10
        SetTimer, ForgeLoop, Off ; Выключаем цикл
    }
    SetTimer, RemoveToolTip, -2000
return

; --- САМ ЦИКЛ КРАФТА ---
ForgeLoop:
    ; 1. Тыкаем на кнопку "Forge" внизу справа
    Click, 1600, 1060
    
    ; Ждем 1.5 секунды, пока прогрузится анимация ковки
    Sleep, 50 

    ; Если пока шла анимация, ты нажал паузу — стопаем круг
    if (!isForging)
        return

    ; 2. Тыкаем на кнопку "Done" по центру (из скриншота image_32ee20.jpg)
    Click, 960, 830
    
    ; Ждем 0.8 секунды, пока закроется плашка с созданным оружием
    Sleep, 50 
return

; --- ПОЛНОЕ ЗАКРЫТИЕ СКРИПТА (Вторая боковая кнопка мыши) ---
XButton2::
    ToolTip, ❌ МАКРОС ЗАКРЫТ, 10, 10
    Sleep, 1000
    ExitApp
return

RemoveToolTip:
    ToolTip
return