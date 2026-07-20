@echo off
cd /d "%~dp0"
title RAT6 CKVN - TOTAL RECOVERY
color 0B
echo ======================================================
echo    RAT6 CKVN - TOTAL RECOVERY ACTIVE
echo ======================================================
echo.

:loop
echo [%date% %time%] Khoi chay Toan bo He thong (Venv)...
.\ckvnvenv\Scripts\python.exe main.py

echo.
echo [CRITICAL] Toan bo He thong vua bi tat hoac bi Crash!
echo [%date% %time%] Ghi log su co va khoi chay lai sau 10 giay...
echo ------------------------------------------------------
echo [%date% %time%] SYSTEM EXIT DETECTED >> data/logs/system_watchdog.log
timeout /t 10
goto loop
