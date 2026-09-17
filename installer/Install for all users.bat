@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install for all users.ps1"
set "result=%ERRORLEVEL%"
pause
exit /b %result%
