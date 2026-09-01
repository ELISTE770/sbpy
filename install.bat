@echo off
rem התקנה בקליק אחד. אפשר גם: install.bat -Dev  /  install.bat -Uninstall
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
