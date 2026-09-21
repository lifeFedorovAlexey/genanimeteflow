from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config import REPO_ROOT


_RUNTIME_STATUS_CACHE: dict[tuple[str, str], tuple[float, dict[str, object]]] = {}
_RUNTIME_STATUS_TTL_SECONDS = 20.0


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    repository: str
    model_id: str
    license: str
    worker_root_env: str
    python_env: str
    fields: dict


class ModelRegistry:
    def __init__(self, path: Path | None = None) -> None:
        registry_path = path or REPO_ROOT / "models" / "registry.json"
        with registry_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        self._models = [ModelSpec(id=item["id"], provider=item["provider"], repository=item["repository"], model_id=item["model_id"], license=item["license"], worker_root_env=item["worker_root_env"], python_env=item["python_env"], fields=item) for item in raw["models"]]

    def all(self) -> list[ModelSpec]:
        return list(self._models)

    @staticmethod
    def _runtime_status(root: Path, python_executable: Path) -> dict[str, object]:
        cache_key = (str(root), str(python_executable))
        cached = _RUNTIME_STATUS_CACHE.get(cache_key)
        now = time.monotonic()
        if cached and now - cached[0] < _RUNTIME_STATUS_TTL_SECONDS:
            return cached[1]
        probe = """
import os
os.environ['NO_ALBUMENTATIONS_UPDATE'] = '1'
import torch
from texture_baker import TextureBaker
from uv_unwrapper import Unwrapper
from transparent_background import Remover
from spar3d.system import SPAR3D
print('cuda=' + str(torch.cuda.is_available()))
try:
    from huggingface_hub import get_hf_file_metadata, hf_hub_download, hf_hub_url
    try:
        cached = hf_hub_download(
            'stabilityai/stable-point-aware-3d',
            filename='model.safetensors',
            local_files_only=True,
        )
        print('model_access=local_cache:' + str(os.path.getsize(cached)))
    except Exception:
        get_hf_file_metadata(hf_hub_url('stabilityai/stable-point-aware-3d', 'model.safetensors'), timeout=10)
        print('model_access=ok')
except Exception as error:
    response = getattr(error, 'response', None)
    status_code = getattr(response, 'status_code', None)
    print('model_access=' + (f'http_{status_code}' if status_code else type(error).__name__))
"""
        command = [str(python_executable), "-c", probe]
        try:
            completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            status: dict[str, object] = {"ready": False, "reason": f"SPAR3D environment could not start: {error}"}
        else:
            output = f"{completed.stdout}\n{completed.stderr}".strip()
            if completed.returncode != 0:
                last_line = next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "unknown import failure")
                status = {"ready": False, "reason": f"SPAR3D dependencies are not ready: {last_line}"}
            elif "cuda=True" not in completed.stdout:
                status = {"ready": False, "reason": "SPAR3D Python cannot use CUDA; install a CUDA-enabled PyTorch build"}
            elif not any(line.startswith("model_access=ok") or line.startswith("model_access=local_cache:") for line in completed.stdout.splitlines()):
                access_line = next((line.strip() for line in completed.stdout.splitlines() if line.startswith("model_access=")), "model_access=unknown")
                if access_line == "model_access=http_401" or access_line == "model_access=http_403":
                    reason = "Accept the SPAR3D model terms and run huggingface-cli login in the SPAR3D environment"
                else:
                    reason = f"SPAR3D model access check failed: {access_line.removeprefix('model_access=')}"
                status = {"ready": False, "reason": reason, "model_access": access_line.removeprefix("model_access=")}
            else:
                access_line = next((line.strip() for line in completed.stdout.splitlines() if line.startswith("model_access=")), "model_access=ok")
                status = {"ready": True, "reason": None, "model_access": access_line.removeprefix("model_access=")}
        _RUNTIME_STATUS_CACHE[cache_key] = (now, status)
        return status

    def status(self) -> list[dict]:
        result = []
        for model in self._models:
            root_value = os.getenv(model.worker_root_env, "")
            root = Path(root_value).expanduser() if root_value else None
            python_value = os.getenv(model.python_env, "")
            python_executable = Path(python_value).expanduser() if python_value else None
            checkout_ready = bool(root and root.is_dir() and (root / "run.py").is_file())
            runtime: dict[str, object] = {"ready": False, "reason": None}
            if checkout_ready and python_executable and python_executable.is_file():
                runtime = self._runtime_status(root, python_executable)
            if not root_value:
                reason = f"Set {model.worker_root_env} to the official checkout"
            elif not checkout_ready:
                reason = f"Official checkout is incomplete: run.py was not found under {root}"
            elif not python_value:
                reason = f"Set {model.python_env} to the isolated Python executable"
            elif not python_executable or not python_executable.is_file():
                reason = f"Configured Python executable was not found: {python_value}"
            else:
                reason = runtime["reason"]
            installed = bool(checkout_ready and runtime["ready"])
            result.append({"id": model.id, "provider": model.provider, "model_id": model.model_id, "repository": model.repository, "license": model.license, "installed": installed, "root": str(root) if root else None, "python": str(python_executable) if python_executable else None, "checkout_ready": checkout_ready, "runtime_ready": runtime["ready"], "reason": reason})
        return result
