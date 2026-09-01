@echo off
chcp 65001 >nul
title Building SBpy Setup Wizard Installer...
echo ======================================================
echo    Building SBpy_Setup.exe (Graphical Setup Wizard)
echo ======================================================
echo.

if exist ".build_venv\Scripts\python.exe" (
    ".build_venv\Scripts\python.exe" build_installer.py
) else (
    python build_installer.py
)

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Installer compiled successfully: dist\SBpy_Setup.exe
) else (
    echo.
    echo [ERROR] Build failed with exit code %ERRORLEVEL%.
)

echo.
pause
