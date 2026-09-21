# Local model setup

Character Factory does not download gated model weights implicitly. Configure each worker only after accepting the upstream license and model access terms, then run `scripts/check_workers.ps1`.

## SPAR3D (single-image geometry)

Official repository: https://github.com/Stability-AI/stable-point-aware-3d

SPAR3D documents an official `run.py` CLI. Its documented low-VRAM mode is expected to use roughly 7 GB instead of roughly 10.5 GB, but the application still records the real peak measured by the worker. Windows support is documented as experimental by the upstream project.

On Windows, use the repository installer to clone the official checkout, create an isolated environment, install CUDA PyTorch for the RTX 4070 and persist the two paths:

```powershell
.\scripts\install_spar3d.ps1 -PersistPaths
```

The model is gated: before the first generation, accept access to `stabilityai/stable-point-aware-3d` on Hugging Face and log in with a read token in the SPAR3D environment. The installer intentionally does not ask for, store, or transmit a token.

For an existing installation, these are the two paths Character Factory uses:

```powershell
$env:SPAR3D_ROOT = 'D:\models\stable-point-aware-3d'
$env:SPAR3D_PYTHON = 'D:\models\venvs\spar3d\Scripts\python.exe'
```

Install the official repository requirements and authenticate to Hugging Face as required by the upstream project. The Character Factory adapter calls `run.py` with the actual image, output directory, texture resolution, low-VRAM flag and remesh settings, then requires a non-empty `0/mesh.glb` result.

## Hunyuan3D multiview

Official repository: https://github.com/Tencent-Hunyuan/Hunyuan3D-2

The upstream repository documents the `tencent/Hunyuan3D-2mv` model family and the `hunyuan3d-dit-v2-mv` subfolder. Shape generation is documented at about 6 GB VRAM; shape plus texture is documented at about 16 GB, which exceeds the target RTX 4070 budget for a combined stage. The provider will therefore remain explicit about which sub-stage is enabled and will not claim a textured result when only shape generation is installed.

## UniRig

Official repository: https://github.com/VAST-AI-Research/UniRig

UniRig publishes separate skeleton and skinning inference flows and states a minimum of 8 GB VRAM for generation. The rig worker will be enabled only after the official checkout and compatible checkpoint are present.

## License and provenance

Every model entry is recorded in `models/registry.json` with its official repository, model identifier and license note. Model weights are user-owned external assets and are intentionally excluded from Git, job exports and automated setup.
