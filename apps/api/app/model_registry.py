from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .config import REPO_ROOT


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

    def status(self) -> list[dict]:
        result = []
        for model in self._models:
            root_value = os.getenv(model.worker_root_env, "")
            root = Path(root_value).expanduser() if root_value else None
            installed = bool(root and root.is_dir())
            result.append({"id": model.id, "provider": model.provider, "model_id": model.model_id, "repository": model.repository, "license": model.license, "installed": installed, "root": str(root) if root else None, "python": os.getenv(model.python_env), "reason": None if installed else f"Set {model.worker_root_env} to an installed official checkout"})
        return result
