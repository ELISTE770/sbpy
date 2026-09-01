@echo off
chcp 65001 >nul
title Building SBpy Executable...
echo ======================================================
echo    Building SBpy Standalone Executable (.EXE)
echo ======================================================
echo.

if exist ".build_venv\Scripts\python.exe" (
    ".build_venv\Scripts\python.exe" build_exe.py
) else (
    python build_exe.py
)

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] SBpy compiled successfully to dist\sbpy.exe!
    echo [SUCCESS] Desktop shortcut created.
) else (
    echo.
    echo [ERROR] Build failed with exit code %ERRORLEVEL%.
)

echo.
pause
