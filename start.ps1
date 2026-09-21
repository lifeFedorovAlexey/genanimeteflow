$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { throw "Run .\setup.ps1 first to create the project virtual environment" }
$env:PYTHONPATH = Join-Path $Root "apps/api"
Write-Host "Starting Character Factory API on http://127.0.0.1:8000" -ForegroundColor Cyan
$api = Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $Root -PassThru
try { Push-Location (Join-Path $Root "apps/web"); Write-Host "Starting Character Factory UI on http://127.0.0.1:5173" -ForegroundColor Cyan; npm run dev } finally { Pop-Location; if ($api -and !$api.HasExited) { Stop-Process -Id $api.Id } }
