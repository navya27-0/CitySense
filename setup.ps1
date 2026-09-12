Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  CitySense - Self-Contained Environment Setup" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

try {
    $pyVer = & python --version 2>&1
    Write-Host "[*] Found Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Error "Python is not found in PATH. Please install Python 3.10+ and add to PATH."
    exit 1
}

if (-not (Test-Path "venv")) {
    Write-Host "[*] Creating local virtual environment in .\venv..." -ForegroundColor Yellow
    & python -m venv venv
} else {
    Write-Host "[*] Local virtual environment already exists in .\venv" -ForegroundColor Green
}

$venvPython = ".\venv\Scripts\python.exe"

Write-Host "[*] Upgrading pip..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip

Write-Host "[*] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
& $venvPython -m pip install -r requirements.txt

Write-Host "[*] Initializing baseline AI models..." -ForegroundColor Yellow
& $venvPython -c "from ultralytics import YOLO; YOLO('models/yolov8n.pt')"

Write-Host "[*] Initializing demo datasets and evidence fixtures..." -ForegroundColor Yellow
& $venvPython scripts\seed_demo_dataset.py

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "  Run CitySense anytime using: .\run.ps1" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
