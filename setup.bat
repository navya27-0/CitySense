@echo off
setlocal
cd /d "%~dp0"

echo =======================================================
echo   CitySense - Self-Contained Environment Setup
echo =======================================================
echo.

set "PY_CMD="
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
) else (
    py --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PY_CMD=py"
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python was not found on your system.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [*] Using system Python command: %PY_CMD%

if not exist "venv\Scripts\python.exe" (
    echo [*] Creating local virtual environment (venv)...
    %PY_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [*] Virtual environment already exists in .\venv
)

echo [*] Upgrading pip...
call venv\Scripts\python.exe -m pip install --upgrade pip

echo [*] Installing project dependencies from requirements.txt...
call venv\Scripts\pip.exe install -r requirements.txt

echo [*] Initializing baseline AI models...
call venv\Scripts\python.exe -c "from ultralytics import YOLO; YOLO('models/yolov8n.pt')"

echo [*] Initializing demo datasets and evidence fixtures...
call venv\Scripts\python.exe scripts\seed_demo_dataset.py

echo.
echo =======================================================
echo   Setup Complete!
echo   Run CitySense anytime using: run.bat
echo =======================================================
pause
