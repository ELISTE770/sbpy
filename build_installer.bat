@echo off
chcp 65001 >nul
title Building SBpy Setup with Inno Setup...
echo ======================================================
echo    Building SBpy_Setup.exe using Inno Setup 6
echo ======================================================
echo.

rem Step 1: Rebuild sbpy.exe from latest source code
echo [*] Rebuilding sbpy.exe from latest code...
if exist ".build_venv\Scripts\python.exe" (
    ".build_venv\Scripts\python.exe" build_exe.py
) else (
    python build_exe.py
)

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed compiling sbpy.exe.
    pause
    exit /b %ERRORLEVEL%
)

rem Step 2: Compile installer.iss using Inno Setup ISCC
echo.
echo [*] Compiling Inno Setup Script (installer.iss)...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if exist "%ISCC%" (
    "%ISCC%" installer.iss
) else (
    echo [ERROR] ISCC.exe not found. Please install Inno Setup 6.
    pause
    exit /b 1
)

if %ERRORLEVEL% equ 0 (
    echo.
    echo ======================================================
    echo [SUCCESS] SBpy_Setup.exe created successfully in dist\
    echo ======================================================
) else (
    echo.
    echo [ERROR] Inno Setup compilation failed with code %ERRORLEVEL%.
)

echo.
pause
