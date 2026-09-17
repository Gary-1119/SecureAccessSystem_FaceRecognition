@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall for all users.ps1"
set "result=%ERRORLEVEL%"
pause
exit /b %result%
