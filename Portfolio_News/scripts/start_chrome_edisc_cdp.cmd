@echo off
REM Dedicated Chrome for e-disclosure CDP. NOT the default profile (banks/passwords).
set PORT=9222
set DATADIR=%LOCALAPPDATA%\Portfolio_News\chrome-edisc
set CHROME=
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe
if "%CHROME%"=="" (
  echo Chrome.exe not found.
  exit /b 1
)
if not exist "%DATADIR%" mkdir "%DATADIR%"
echo CDP: http://127.0.0.1:%PORT%
echo Profile: %DATADIR%
echo Pass the e-disclosure JS-check once in THIS window, then poll / once.
start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%DATADIR%" --no-first-run --no-default-browser-check "https://www.e-disclosure.ru/portal/company.aspx?id=3043"
