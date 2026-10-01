@echo off
cd /d "%~dp0"
call npm.cmd start
exit /b %errorlevel%
