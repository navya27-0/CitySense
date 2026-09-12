@echo off
setlocal
cd /d "%~dp0"

echo =======================================================
echo   CitySense - Self-Contained Environment Setup
echo =======================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in PATH. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

if not exist "venv" (
    echo [*] Creating local virtual environment (venv)...
    python -m venv venv
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
