@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title RAT VN30 - CKPS
:menu
cls
echo ========================================
echo              RAT VN30 - CKPS
echo ========================================
echo   1. Mo app
echo   2. Blackbox
echo   3. Ra soat / cai moi truong
echo   4. Update
echo   5. Nap preset
echo   6. Thoat
echo.
choice /c 123456 /n /m "Chon [1/2/3/4/5/6]: "
if errorlevel 6 exit /b 0
if errorlevel 5 goto preset
if errorlevel 4 goto update
if errorlevel 3 goto install
if errorlevel 2 goto blackbox
if errorlevel 1 goto start
goto menu
:start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Start
if errorlevel 1 pause
goto menu
:blackbox
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Blackbox
if errorlevel 1 pause
goto menu
:install
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Install
pause
goto menu
:preset
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Preset
if errorlevel 1 pause
goto menu
:update
start "RAT - Update" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Update
exit /b 0
