@echo off
title Smiling-lemon Bot (@ShporaNMT_bot) - RUNNING
if exist "C:\Users\limon\shpora-network\venv\Scripts\python.exe" (
    cd /d "C:\Users\limon\shpora-network"
    echo ========================================================
    echo   SMILING-LEMON BOT IS STARTING... DO NOT CLOSE WINDOW
    echo ========================================================
    "C:\Users\limon\shpora-network\venv\Scripts\python.exe" run_polling.py
    pause
    exit /b
)
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" run_polling.py
    pause
    exit /b
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_polling.py
    pause
    exit /b
)
python -m venv venv
"venv\Scripts\python.exe" -m pip install -q --upgrade pip
"venv\Scripts\python.exe" -m pip install -q -r requirements.txt
"venv\Scripts\python.exe" -m playwright install chromium
"venv\Scripts\python.exe" run_polling.py
pause
