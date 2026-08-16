@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install for this user.ps1"
pause
