# Local model setup

Character Factory does not download gated model weights implicitly. Configure each worker only after accepting the upstream license and model access terms, then run `scripts/check_workers.ps1`.

## SPAR3D (single-image geometry)

Official repository: https://github.com/Stability-AI/stable-point-aware-3d

SPAR3D documents an official `run.py` CLI. Its documented low-VRAM mode is expected to use roughly 7 GB instead of roughly 10.5 GB, but the application still records the real peak measured by the worker. Windows support is documented as experimental by the upstream project.

On Windows, use the repository installer to clone the official checkout, create an isolated environment, install CUDA PyTorch for the RTX 4070 and persist the two paths:

```powershell
.\scripts\install_spar3d.ps1 -PersistPaths
```

The Windows installer uses the verified Python 3.11 / PyTorch 2.11.0 + CUDA 12.8 / torchvision 0.26.0 combination. It selects Visual Studio 2022 and the Windows SDK resource compiler, disables Unix-only native flags, and builds the texture/UV extensions without pip build isolation. CLIP and AlphaCLIP also build in the prepared environment, with setuptools 69.5.1. Flet 0.24.1, packaging 23.2 and wheel 0.43.0 avoid incompatible transitive updates.

The tracked `scripts/patches/spar3d-cuda-headers.patch` replaces the unused Python binding header in the CUDA source with `torch/types.h`. This resolves the observed CUDA/MSVC error in PyTorch's `compiled_autograd.h` without changing the reconstruction algorithm. The source patch is applied once and checked before subsequent installs. This separation of CUDA code from Python bindings follows [PyTorch extension guidance](https://docs.pytorch.org/docs/2.14/cpp_extension.html).

Successful setup requires `pip check`, an actual CUDA texture bake, a native UV unwrap and the official CLI's `--help` command to pass. Repeat the offline verification with:

```powershell
& 'D:\models\venvs\spar3d\Scripts\python.exe' .\scripts\verify_spar3d.py 'D:\models\stable-point-aware-3d'
```

Use `-SkipTorch` to reuse the installed CUDA PyTorch, `-SkipRequirements` to skip ordinary Python dependencies, or `-RebuildNative` to rebuild installed native modules after changing PyTorch/toolchains. None of these switches skips final runtime verification. Triangle and quad remeshing dependencies are included; the optional upstream Gradio demo is not needed by Character Factory.

The model is gated: before the first generation, accept access to `stabilityai/stable-point-aware-3d` on Hugging Face and log in with a read token in the SPAR3D environment. The installer intentionally does not ask for, store, or transmit a token.

Open [the model access page](https://huggingface.co/stabilityai/stable-point-aware-3d), accept its terms in your own account, then authenticate locally:

```powershell
& 'D:\models\venvs\spar3d\Scripts\huggingface-cli.exe' login
```

Do not paste the token into a chat. Adding `--check-model-access` to the verification command checks access without downloading weights or printing credentials. HTTP 401/403 at this stage indicates a model-access step, not a broken dependency install. Passing the offline checks does not imply a complete image-to-mesh inference has run.

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
