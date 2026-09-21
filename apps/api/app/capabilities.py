from __future__ import annotations

import shutil


def capabilities() -> dict:
    blender = shutil.which("blender")
    return {
        "providers": {
            "AUTO": {"available": False, "reason": "No local geometry model has been installed yet"},
            "HunyuanMultiviewProvider": {"available": False, "reason": "Install the pinned Hunyuan worker and model weights"},
            "Spar3DProvider": {"available": False, "reason": "Install the pinned SPAR3D worker and model weights"},
        },
        "stages": {
            "references": {"available": True, "description": "Validate, crop, alpha-process, normalize and persist reference images"},
            "geometry": {"available": False, "reason": "A real local geometry provider is required; no weights are present"},
            "textures": {"available": False, "reason": "Depends on a generated mesh and a real texture provider"},
            "retopology": {"available": False, "reason": "Blender is not installed" if not blender else "Retopology worker is not configured"},
            "rig": {"available": False, "reason": "UniRig worker and model weights are not installed"},
            "motions": {"available": False, "reason": "Motion library has not been installed"},
            "export": {"available": False, "reason": "Requires a validated rigged asset"},
        },
    }
