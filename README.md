# genanimeteflow / Character Factory

Local Character Factory foundation for Windows + NVIDIA hardware. The current repository contains a working FastAPI orchestration service and React/TypeScript UI with persistent jobs, hardware diagnostics, reference upload/preprocessing, structured stage state and a serialized single-GPU queue.

## Setup

```powershell
.\setup.ps1
```

The setup script creates `.venv`, installs the Python project dependencies, installs the web dependencies and writes `hardware_profile.json` from live machine diagnostics.

## Start

```powershell
.\start.ps1
```

Open http://127.0.0.1:5173. The API is localhost-only at http://127.0.0.1:8000.

## Current capabilities

- persistent UUID jobs under `jobs/`
- atomic JSON manifests and resumable job state
- live OS/CPU/RAM/NVIDIA/driver/CUDA/Blender/disk diagnostics
- FRONT/LEFT/BACK/RIGHT upload slots with FRONT required
- original reference preservation and real PIL preprocessing
- foreground quality report with GOOD/WARNING/ERROR states
- structured per-stage logs and an SSE event stream
- single-GPU serialization boundary
- GLB mesh integrity validation and extraction of only embedded provider textures
- honest provider capability reporting: unavailable ML stages are not simulated

The model workers, Blender and motion assets must be installed and version-pinned before their stages can be enabled. See [docs/models.md](docs/models.md) and run `scripts/check_workers.ps1`; no generated mesh or animation is bundled or represented as a fake result.
