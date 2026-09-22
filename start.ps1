$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { throw "Run .\setup.ps1 first to create the project virtual environment" }
$envDefaults = @{
  UNIRIG_ROOT = "D:\models\UniRig"
  UNIRIG_BASH = "C:\Windows\System32\wsl.exe"
  UNIRIG_DISTRO = "Ubuntu"
  UNIRIG_WSL_PYTHON = "/opt/unirig-venv/bin/python"
  BLENDER_PATH = "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
  HUNYUAN_ROOT = "D:\models\hunyuan3d-2"
  HUNYUAN_PYTHON = "D:\models\venvs\hunyuan\Scripts\python.exe"
  HUNYUAN_SHAPE_MODEL_PATH = "D:\models\hunyuan-weights\Hunyuan3D-2mv"
  HUNYUAN_SINGLE_MODEL_PATH = "D:\models\hunyuan-weights\Hunyuan3D-2"
  HUNYUAN_PAINT_MODEL_PATH = "D:\models\hunyuan-weights\Hunyuan3D-2"
  DINOV3_MODEL_PATH = "C:\Users\life\.cache\huggingface\dinov3-vitl16-pretrain-lvd1689m"
  DINOV3_PYTHON = "D:\models\venvs\hunyuan\Scripts\python.exe"
}
foreach ($entry in $envDefaults.GetEnumerator()) {
  $current = [Environment]::GetEnvironmentVariable($entry.Key, "Process")
  $pathLike = $entry.Key -notin @("UNIRIG_BASH", "UNIRIG_DISTRO", "UNIRIG_WSL_PYTHON")
  if ([string]::IsNullOrWhiteSpace($current) -and ((-not $pathLike) -or (Test-Path -LiteralPath $entry.Value))) {
    Set-Item -Path "Env:$($entry.Key)" -Value $entry.Value
  }
}
$env:PYTHONPATH = Join-Path $Root "apps/api"
Write-Host "Starting Character Factory API on http://127.0.0.1:8000" -ForegroundColor Cyan
$api = Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $Root -PassThru
try { Push-Location (Join-Path $Root "apps/web"); Write-Host "Starting Character Factory UI on http://127.0.0.1:5173" -ForegroundColor Cyan; npm run dev } finally { Pop-Location; if ($api -and !$api.HasExited) { Stop-Process -Id $api.Id } }
