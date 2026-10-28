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
echo   3. Preview mau - 1 Long, khong can token
echo   4. Cai dat / sua moi truong
echo   5. Kiem thu offline
echo   0. Thoat
echo.
choice /c 123450 /n /m "Chon [1/2/3/4/5/0]: "
if errorlevel 6 exit /b 0
if errorlevel 5 goto check
if errorlevel 4 goto install
if errorlevel 3 goto demo
if errorlevel 2 goto backend
if errorlevel 1 goto start
goto menu
:start
start "RAT - Giao dich" /b powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Start
goto menu
:backend
start "RAT - Tin hieu" /b powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Backend
goto menu
:demo
start "RAT - Preview mau" /b powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Demo
goto menu
:install
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Install
pause
goto menu
:check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\launcher.ps1" -Action Check
pause
goto menu
