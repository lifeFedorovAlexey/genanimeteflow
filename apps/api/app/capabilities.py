from __future__ import annotations

import shutil

from .model_registry import ModelRegistry


def capabilities() -> dict:
    blender = shutil.which("blender")
    models = ModelRegistry().status()
    spar3d = next(item for item in models if item["id"] == "spar3d")
    return {
        "providers": {
            "AUTO": {"available": spar3d["installed"], "reason": None if spar3d["installed"] else spar3d["reason"]},
            "HunyuanMultiviewProvider": {"available": False, "reason": "The multiview worker is not enabled until its official checkout and model weights are installed"},
            "Spar3DProvider": {"available": spar3d["installed"], "reason": None if spar3d["installed"] else spar3d["reason"]},
        },
        "stages": {
            "references": {"available": True, "description": "Validate, crop, alpha-process, normalize and persist reference images"},
            "geometry": {"available": spar3d["installed"], "reason": None if spar3d["installed"] else spar3d["reason"]},
            "textures": {"available": False, "reason": "Depends on a generated mesh and a real texture provider"},
            "retopology": {"available": False, "reason": "Blender is not installed" if not blender else "Retopology worker is not configured"},
            "rig": {"available": False, "reason": "UniRig worker and model weights are not installed"},
            "motions": {"available": False, "reason": "Motion library has not been installed"},
            "export": {"available": False, "reason": "Requires a validated rigged asset"},
        },
        "models": models,
    }
