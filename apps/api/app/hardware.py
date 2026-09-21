from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from .config import HARDWARE_PROFILE
from .storage import atomic_write_json


def _command_output(command: list[str], timeout: float = 5.0) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _nvidia() -> dict[str, Any]:
    output = _command_output([
        "nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap", "--format=csv,noheader,nounits"
    ])
    gpus: list[dict[str, Any]] = []
    if output:
        for line in output.splitlines():
            fields = [part.strip() for part in line.split(",")]
            if len(fields) >= 4:
                try:
                    memory_mb = float(fields[1])
                except ValueError:
                    memory_mb = None
                gpus.append({"name": fields[0], "vram_mb": memory_mb, "driver": fields[2], "compute_capability": fields[3]})
    return {"available": bool(gpus), "gpus": gpus, "nvml_available": bool(output)}


def detect_hardware() -> dict[str, Any]:
    disk = shutil.disk_usage(Path.cwd())
    blender = shutil.which("blender")
    profile: dict[str, Any] = {
        "detected_at": datetime.now(UTC).isoformat(),
        "os": {"system": platform.system(), "release": platform.release(), "version": platform.version(), "machine": platform.machine()},
        "cpu": {"logical_count": psutil.cpu_count(), "physical_count": psutil.cpu_count(logical=False), "name": platform.processor()},
        "ram": {"total_bytes": psutil.virtual_memory().total, "total_gb": round(psutil.virtual_memory().total / 1024**3, 2)},
        "gpu": _nvidia(),
        "python": {"version": sys.version, "executable": sys.executable},
        "cuda": {"torch_available": False, "torch_cuda_available": False},
        "blender": {"available": bool(blender), "path": blender},
        "wsl": {"available": "microsoft" in platform.release().lower() or bool(os.getenv("WSL_DISTRO_NAME")), "distribution": os.getenv("WSL_DISTRO_NAME")},
        "disk": {"free_bytes": disk.free, "free_gb": round(disk.free / 1024**3, 2)},
    }
    try:
        import torch  # type: ignore
    except ImportError:
        torch = None
    else:
        profile["cuda"] = {"torch_available": True, "torch_version": torch.__version__, "torch_cuda_available": bool(torch.cuda.is_available()), "torch_cuda_version": torch.version.cuda}
    gpu_vram = (profile["gpu"].get("gpus") or [{}])[0].get("vram_mb") or 0
    profile["recommendation"] = "BALANCED" if gpu_vram >= 9000 else "SAFE"
    atomic_write_json(HARDWARE_PROFILE, profile)
    return profile
