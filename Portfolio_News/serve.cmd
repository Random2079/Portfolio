@echo off
rem Same launcher as react sibling — walk up from cwd, then serve.
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
exit /b 1
