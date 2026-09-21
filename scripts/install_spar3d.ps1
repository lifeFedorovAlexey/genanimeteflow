[CmdletBinding()]
param(
  [string]$InstallRoot = "D:\models\stable-point-aware-3d",
  [string]$VenvRoot = "D:\models\venvs\spar3d",
  [string]$PythonCommand = "python",
  [switch]$SkipTorch,
  [switch]$SkipRequirements,
  [switch]$RebuildNative,
  [switch]$PersistPaths
)

$ErrorActionPreference = "Stop"
$OfficialRepository = "https://github.com/Stability-AI/stable-point-aware-3d.git"
$BasePython = (& $PythonCommand -c "import sys; print(sys._base_executable)" | Select-Object -First 1).Trim()
if (-not $BasePython -or -not (Test-Path -LiteralPath $BasePython -PathType Leaf)) {
  throw "Unable to locate the base CPython executable behind $PythonCommand"
}

function Invoke-Checked {
  param([scriptblock]$Command, [string]$FailureMessage)
  & $Command
  if ($LASTEXITCODE -ne 0) { throw $FailureMessage }
}

function Import-VisualStudioBuildEnvironment {
  $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
  if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) {
    throw "Visual Studio Build Tools with the C++ workload are required to compile SPAR3D texture_baker."
  }
  # CUDA 12.8 supports the VS 2022 compiler; prefer it over a newer VS release
  # when both are installed (the latter can expose an unsupported host compiler).
  $installationRoot = [string](& $vswhere -latest -products * -version "[17.0,18.0)" -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
  $installationRoot = $installationRoot.Trim()
  if (-not $installationRoot) {
    throw "Visual Studio 2022 C++ Build Tools are required for this CUDA 12.8 environment."
  }
  $developerCommand = Join-Path $installationRoot "Common7\Tools\VsDevCmd.bat"
  if (-not (Test-Path -LiteralPath $developerCommand -PathType Leaf)) { throw "VsDevCmd.bat was not found." }
  $environmentLines = & cmd.exe /d /s /c "call `"$developerCommand`" -arch=x64 >nul && set"
  foreach ($line in $environmentLines) {
    if ($line -match "^([^=]+)=(.*)$") {
      if ($matches[1] -ceq "Path") { continue }
      Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
    }
  }
  $compilerPath = $null
  $toolRoot = Join-Path $installationRoot "VC\Tools\MSVC"
  foreach ($toolset in Get-ChildItem -LiteralPath $toolRoot -Directory | Sort-Object Name -Descending) {
    $candidate = Join-Path $toolset.FullName "bin\Hostx64\x64\cl.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
      $compilerPath = $candidate
      break
    }
  }
  if (-not $compilerPath) {
    throw "Visual Studio C++ compiler was not found in the x64 build environment."
  }
  $script:CompilerPath = $compilerPath
  $sdkBinRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
  $sdkBin = Get-ChildItem -LiteralPath $sdkBinRoot -Directory | Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName "x64" } |
    Where-Object { (Test-Path (Join-Path $_ "rc.exe")) -and (Test-Path (Join-Path $_ "mt.exe")) } |
    Select-Object -First 1
  if (-not $sdkBin) { throw "Windows SDK resource compiler rc.exe was not found." }
  $script:BuildPath = $sdkBin + ";" + $env:PATH
  $env:DISTUTILS_USE_SDK = "1"
  $env:MSSdk = "1"
}

function Install-Spar3dNativeModules {
  $cudaPatch = Join-Path $PSScriptRoot "patches\spar3d-cuda-headers.patch"
  $previousErrorAction = $ErrorActionPreference
  try {
    # These probes are expected to fail on a fresh checkout/environment. Windows
    # PowerShell represents native stderr as ErrorRecords, even when redirected.
    $ErrorActionPreference = "Continue"
    & git -C $InstallRoot apply --reverse --check $cudaPatch 2>$null
    $patchApplied = $LASTEXITCODE -eq 0
    & $venvPython -c "import torch; from texture_baker import TextureBaker; from uv_unwrapper import Unwrapper" 2>$null
    $nativeInstalled = $LASTEXITCODE -eq 0
  }
  finally { $ErrorActionPreference = $previousErrorAction }
  if (-not $patchApplied) {
    Invoke-Checked { git -C $InstallRoot apply --check $cudaPatch } "SPAR3D source differs from the supported CUDA patch; inspect before updating."
    Invoke-Checked { git -C $InstallRoot apply $cudaPatch } "Unable to apply the Windows CUDA header fix."
  }
  if ($nativeInstalled -and -not $RebuildNative) {
    Write-Host "Native modules already installed; the final check will exercise their kernels."
    return
  }
  Import-VisualStudioBuildEnvironment
  $sitePackages = (& $venvPython -c "import site; print(site.getsitepackages()[0])" | Select-Object -First 1).Trim()
  $compilerDirectory = Split-Path -Parent $CompilerPath
  $buildHook = Join-Path $sitePackages "character_factory_build_env.pth"
  if (Test-Path -LiteralPath $buildHook) { throw "A SPAR3D build hook already exists at $buildHook. Check for a concurrent installer first." }
  $pythonCompilerPath = $CompilerPath.Replace("\", "\\")
  $pythonCompilerDirectory = ($compilerDirectory + ";" + $BuildPath).Replace("\", "\\").Replace("'", "\'")
  [System.IO.File]::WriteAllText($buildHook, "import os; os.environ.update({'PATH': r'$pythonCompilerDirectory;' + os.environ.get('PATH', ''), 'CC': r'$pythonCompilerPath', 'CXX': r'$pythonCompilerPath', 'CUDAHOSTCXX': r'$pythonCompilerPath', 'DISTUTILS_USE_SDK': '1', 'MSSdk': '1'})", [System.Text.UTF8Encoding]::new($false))
  $previousNativeArch = $env:USE_NATIVE_ARCH
  try {
    # The upstream uv_unwrapper setup uses Unix-only optimization flags when this
    # variable is unset. Disable them for the MSVC build on Windows.
    $env:USE_NATIVE_ARCH = "0"
    Invoke-Checked { & $venvPython -m pip install --no-build-isolation (Join-Path $InstallRoot "texture_baker") } "Unable to install the official SPAR3D texture module."
    Invoke-Checked { & $venvPython -m pip install --no-build-isolation (Join-Path $InstallRoot "uv_unwrapper") } "Unable to install the official SPAR3D UV module."
  }
  finally {
    Remove-Item -LiteralPath $buildHook -Force -ErrorAction SilentlyContinue
    $env:USE_NATIVE_ARCH = $previousNativeArch
  }
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

Invoke-Checked { & $BasePython -m venv --upgrade $VenvRoot } "Unable to create or upgrade the SPAR3D Python environment."

$venvPython = Join-Path $VenvRoot "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
  throw "SPAR3D Python executable was not found at $venvPython"
}

Invoke-Checked { & $venvPython -m pip install pip==26.2.1 setuptools==69.5.1 wheel==0.43.0 packaging==23.2 ninja } "Unable to prepare pip for SPAR3D."
if (-not $SkipTorch) {
  Invoke-Checked { & $venvPython -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128 } "Unable to install CUDA PyTorch for SPAR3D."
}
if (-not $SkipRequirements) {
  $requirements = Get-Content -LiteralPath (Join-Path $InstallRoot "requirements.txt")
  $sourceRequirements = @("git+https://github.com/openai/CLIP.git", "git+https://github.com/SunzeY/AlphaCLIP.git")
  $packageRequirements = @($requirements | Where-Object { $_ -notin @("./texture_baker/", "./uv_unwrapper/") -and $_ -notin $sourceRequirements }) + "flet==0.24.1"
  $temporaryRequirements = [System.IO.Path]::GetTempFileName()
  Set-Content -LiteralPath $temporaryRequirements -Value $packageRequirements -Encoding utf8
  try {
    Invoke-Checked { & $venvPython -m pip install -r $temporaryRequirements } "Unable to install the official SPAR3D Python requirements."
    Invoke-Checked { & $venvPython -m pip install --no-build-isolation @sourceRequirements } "Unable to install the official SPAR3D CLIP modules."
    Invoke-Checked { & $venvPython -m pip install -r (Join-Path $InstallRoot "requirements-remesh.txt") } "Unable to install SPAR3D remeshing modules."
    Install-Spar3dNativeModules
  }
  finally {
    Remove-Item -LiteralPath $temporaryRequirements -Force -ErrorAction SilentlyContinue
  }
}
else {
  Install-Spar3dNativeModules
}

Invoke-Checked { & $venvPython -m pip check } "SPAR3D still has conflicting or missing Python dependencies."
Invoke-Checked { & $venvPython (Join-Path $PSScriptRoot "verify_spar3d.py") $InstallRoot } "SPAR3D runtime verification failed. Paths have not been enabled."

if ($PersistPaths) {
  [Environment]::SetEnvironmentVariable("SPAR3D_ROOT", $InstallRoot, "User")
  [Environment]::SetEnvironmentVariable("SPAR3D_PYTHON", $venvPython, "User")
}

Write-Host "SPAR3D dependencies verified: CUDA texture bake, native UV unwrap and official CLI." -ForegroundColor Green
Write-Host "SPAR3D_ROOT=$InstallRoot"
Write-Host "SPAR3D_PYTHON=$venvPython"
Write-Host "Before the first generation, accept access to stabilityai/stable-point-aware-3d on Hugging Face and run:"
Write-Host "  & '$(Join-Path $VenvRoot 'Scripts\huggingface-cli.exe')' login" -ForegroundColor Yellow
Write-Host "Restart Character Factory after setting the user environment variables." -ForegroundColor Yellow
