from __future__ import annotations

import os
from pathlib import Path

from .config import REPO_ROOT


DINOV3_MODEL_ID = "facebook/dinov3-vitl16-pretrain-lvd1689m"


def dinov3_model_path() -> Path | None:
    """Return an explicitly configured or standard local DINOv3 snapshot."""
    configured = os.getenv("DINOV3_MODEL_PATH", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path.home() / ".cache" / "huggingface" / "dinov3-vitl16-pretrain-lvd1689m",
        REPO_ROOT / "models" / "dinov3-vitl16-pretrain-lvd1689m",
    ]
    for candidate in candidates:
        if candidate and (candidate / "config.json").is_file() and (candidate / "model.safetensors").is_file():
            return candidate.resolve()
    return None


def dinov3_runtime() -> dict[str, object]:
    model_path = dinov3_model_path()
    if model_path is None:
        return {
            "available": False,
            "model_id": DINOV3_MODEL_ID,
            "reason": "DINOv3 weights are not cached locally",
        }
    python = os.getenv("DINOV3_PYTHON") or os.getenv("HUNYUAN_PYTHON")
    return {
        "available": bool(python),
        "model_id": DINOV3_MODEL_ID,
        "model_path": str(model_path),
        "python": python,
        "reason": None if python else "Configure DINOV3_PYTHON or HUNYUAN_PYTHON",
    }
