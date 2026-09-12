@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [!] Virtual environment not found in .\venv.
    echo [*] Running setup.bat first...
    call setup.bat
)

echo =======================================================
echo   Launching CitySense Edge AI Dashboard
echo =======================================================
echo.
venv\Scripts\python.exe scripts\run_demo.py %*
pause
