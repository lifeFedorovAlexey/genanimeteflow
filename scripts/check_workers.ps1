$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$checks = @(
  @{ Name = "SPAR3D"; Root = $env:SPAR3D_ROOT; Script = "run.py"; Python = $env:SPAR3D_PYTHON },
  @{ Name = "Hunyuan3D"; Root = $env:HUNYUAN_ROOT; Script = "api_server.py"; Python = $env:HUNYUAN_PYTHON },
  @{ Name = "UniRig"; Root = $env:UNIRIG_ROOT; Script = "run.py"; Python = $env:UNIRIG_PYTHON }
)
foreach ($check in $checks) {
  if (-not $check.Root) { Write-Host "$($check.Name): not configured" -ForegroundColor Yellow; continue }
  $rootPath = [System.IO.Path]::GetFullPath($check.Root)
  $scriptPath = Join-Path $rootPath $check.Script
  if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { Write-Host "$($check.Name): checkout found, expected $($check.Script) missing at $rootPath" -ForegroundColor Red; continue }
  $python = if ($check.Python) { $check.Python } else { "python" }
  $version = & $python --version 2>&1
  Write-Host "$($check.Name): ready at $rootPath ($version)" -ForegroundColor Green
}
Write-Host "No model weights are downloaded by this check." -ForegroundColor Cyan
