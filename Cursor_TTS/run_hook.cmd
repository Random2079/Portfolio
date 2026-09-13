@echo off
setlocal
cd /d "%~dp0"
set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0.cursor\hooks\tts_after_response.py"
