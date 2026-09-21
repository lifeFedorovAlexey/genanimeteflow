[CmdletBinding()]
param(
  [string]$InstallRoot = "D:\models\stable-point-aware-3d",
  [string]$VenvRoot = "D:\models\venvs\spar3d",
  [string]$PythonCommand = "python",
  [switch]$SkipTorch,
  [switch]$SkipRequirements,
  [switch]$PersistPaths
)

$ErrorActionPreference = "Stop"
$OfficialRepository = "https://github.com/Stability-AI/stable-point-aware-3d.git"

function Invoke-Checked {
  param([scriptblock]$Command, [string]$FailureMessage)
  & $Command
  if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

if (-not (Test-Path -LiteralPath $InstallRoot)) {
  $parent = Split-Path -Parent $InstallRoot
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  Invoke-Checked { git clone --depth 1 $OfficialRepository $InstallRoot } "Unable to clone the official SPAR3D repository."
}

$runScript = Join-Path $InstallRoot "run.py"
if (-not (Test-Path -LiteralPath $runScript -PathType Leaf)) {
  throw "SPAR3D checkout is incomplete: run.py was not found at $runScript"
}

if (-not (Test-Path -LiteralPath $VenvRoot)) {
  Invoke-Checked { & $PythonCommand -m venv $VenvRoot } "Unable to create the SPAR3D Python environment."
}

$venvPython = Join-Path $VenvRoot "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
  throw "SPAR3D Python executable was not found at $venvPython"
}

Invoke-Checked { & $venvPython -m pip install --upgrade pip setuptools==69.5.1 wheel } "Unable to prepare pip for SPAR3D."
if (-not $SkipTorch) {
  Invoke-Checked { & $venvPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 } "Unable to install CUDA PyTorch for SPAR3D."
}
if (-not $SkipRequirements) {
  Invoke-Checked { & $venvPython -m pip install -r (Join-Path $InstallRoot "requirements.txt") } "Unable to install the official SPAR3D requirements."
}

if ($PersistPaths) {
  [Environment]::SetEnvironmentVariable("SPAR3D_ROOT", $InstallRoot, "User")
  [Environment]::SetEnvironmentVariable("SPAR3D_PYTHON", $venvPython, "User")
}

$torchReport = & $venvPython -c "import torch; print(f'torch={torch.__version__}; cuda={torch.cuda.is_available()}; device={torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}')" 2>&1
if ($LASTEXITCODE -ne 0) { throw "PyTorch validation failed: $torchReport" }

Write-Host "SPAR3D code and dependencies are installed." -ForegroundColor Green
Write-Host "SPAR3D_ROOT=$InstallRoot"
Write-Host "SPAR3D_PYTHON=$venvPython"
Write-Host "Before the first generation, accept access to stabilityai/stable-point-aware-3d on Hugging Face and run:"
Write-Host "  & '$venvPython' -m huggingface_hub.commands.huggingface_cli login" -ForegroundColor Yellow
Write-Host "Restart Character Factory after setting the user environment variables." -ForegroundColor Yellow
