# genanimeteflow / Character Factory

Локальный Character Factory для Windows + NVIDIA: reference images → geometry → материалы → retopology/UV → UniRig skeleton/weights → licensed motions → animation graph → equipment/clothing/IK → Unit Tester → GLB/FBX export.

Система работает только с реальными локальными результатами. Если модель недоступна, UI показывает причину и не выдаёт заглушку за успешную генерацию.

## Setup

```powershell
.\setup.ps1
```

For WSL/Linux:

```bash
./setup.sh
```

The setup script creates `.venv`, installs the Python project dependencies, installs the web dependencies and writes `hardware_profile.json` from live machine diagnostics.

## Start

```powershell
.\start.ps1
```

Открой URL, который напечатает Vite (обычно http://127.0.0.1:5173; в занятом порту он может быть 5176). API слушает только localhost: http://127.0.0.1:8000.

## Current capabilities

- persistent UUID jobs under `jobs/`, resumable state and atomic manifests
- live OS/CPU/RAM/NVIDIA/driver/CUDA/Blender/disk diagnostics plus used/peak VRAM
- FRONT/LEFT/BACK/RIGHT slots, original preservation, PIL preprocessing and silhouette/T-pose warnings
- official Hunyuan3D-2mv for 2+ views; single FRONT prefers SPAR3D when installed and records an explicit Hunyuan fallback otherwise
- real Hunyuan Paint textures, embedded PBR validation and source-preserving TRIANGLE/QUAD/KEEP_SOURCE retopology
- official UniRig bridge, canonical skeleton/weights validation and Blender retargeting
- licensed local UAL2 motion library, animation graph, equipment sockets, clothing transfer and IK validation
- Unit Tester playback for real embedded GLB actions, keyboard locomotion, wireframe/skeleton/socket/IK debug views
- Blender GLB + FBX export, selected-action filtering, round-trip validation and `unit.manifest.json`
- per-stage logs, SSE job events, single-GPU queue, cancellation and cache cleanup
- no billing/promotional UI and no simulated provider result

## Acceptance verification

Для промежуточного job:

```powershell
.\.venv\Scripts\python.exe scripts\verify_acceptance.py JOB_ID
```

Строгий финальный gate требует четыре реально обработанных ракурса, Hunyuan multiview, GOOD-проверку DINOv3, sword + rifle, clothing и IK:

```powershell
.\.venv\Scripts\python.exe scripts\verify_acceptance.py JOB_ID --full
```

The model workers, Blender and motion assets must be installed and version-pinned before their stages can be enabled. Для SPAR3D: `scripts/install_spar3d.ps1 -PersistPaths`, затем одноразовый Hugging Face login из [docs/models.md](docs/models.md). Windows launcher автоматически подхватывает стандартные локальные пути Hunyuan/UniRig/DINOv3, если они существуют; переменные окружения имеют приоритет. Run `scripts/check_workers.ps1` to verify local workers; no generated mesh or animation is bundled or represented as a fake result.
