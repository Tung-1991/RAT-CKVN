@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title RAT VN30 - CKPS
:menu
cls
echo ========================================
echo              RAT VN30 - CKPS
echo ========================================
echo   1. App giao dich - PAPER / REAL
echo   2. Backend tin hieu - Telegram
echo   3. Cai dat / sua moi truong
echo   4. Kiem thu tu dong
echo   0. Thoat
echo.
choice /c 12340 /n /m "Chon [1/2/3/4/0]: "
if errorlevel 5 exit /b 0
if errorlevel 4 goto check
if errorlevel 3 goto install
if errorlevel 2 goto backend
if errorlevel 1 goto start
goto menu
:start
start "RAT - Giao dich" /b powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Start
goto menu
:backend
start "RAT - Tin hieu" /b powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Backend
goto menu
:install
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Install
pause
goto menu
:check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Check
pause
goto menu
