$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$venvPython = ".\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[!] Virtual environment not found. Running setup.ps1 first..." -ForegroundColor Yellow
    & .\setup.ps1
}

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  Launching CitySense Edge AI Dashboard" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

& $venvPython scripts\run_demo.py @args
