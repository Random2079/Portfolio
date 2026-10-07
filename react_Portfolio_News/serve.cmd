@echo off
rem Find Portfolio_News (package root) by walking up from current directory.
setlocal EnableExtensions
set "D=%CD%"

:loop
if exist "%D%\portfolio_news\__main__.py" goto run
if exist "%D%\Portfolio_News\portfolio_news\__main__.py" (
  set "D=%D%\Portfolio_News"
  goto run
)
set "NEXT="
for %%I in ("%D%\..") do set "NEXT=%%~fI"
if not defined NEXT goto fail
if /i "%NEXT%"=="%D%" goto fail
set "D=%NEXT%"
goto loop

:run
cd /d "%D%"
echo [serve] %CD%
python -m portfolio_news serve %*
exit /b %ERRORLEVEL%

:fail
echo [serve] Portfolio_News not found above: %CD%
echo Expected folder with portfolio_news\__main__.py or sibling Portfolio_News\
exit /b 1
