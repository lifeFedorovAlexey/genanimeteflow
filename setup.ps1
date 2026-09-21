$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Checking local prerequisites..." -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3.11+ is required" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node.js 20+ is required" }
python -m venv (Join-Path $Root ".venv")
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e ".[dev]"
Push-Location (Join-Path $Root "apps/web"); npm install; Pop-Location
$env:PYTHONPATH = Join-Path $Root "apps/api"
python -c "from app.hardware import detect_hardware; import json; print(json.dumps(detect_hardware(), indent=2))"
Write-Host "Setup complete. Run .\start.ps1" -ForegroundColor Green
