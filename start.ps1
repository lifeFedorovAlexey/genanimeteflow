$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $Root "apps/api"
Write-Host "Starting Character Factory API on http://127.0.0.1:8000" -ForegroundColor Cyan
$api = Start-Process -FilePath "python" -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $Root -PassThru
try { Push-Location (Join-Path $Root "apps/web"); Write-Host "Starting Character Factory UI on http://127.0.0.1:5173" -ForegroundColor Cyan; npm run dev } finally { Pop-Location; if ($api -and !$api.HasExited) { Stop-Process -Id $api.Id } }
