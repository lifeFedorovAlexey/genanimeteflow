from __future__ import annotations

import shutil
import os
from pathlib import Path

from .model_registry import ModelRegistry
from .motion_library import MotionLibrary


def capabilities() -> dict:
    blender = shutil.which("blender")
    models = ModelRegistry().status()
    spar3d = next(item for item in models if item["id"] == "spar3d")
    unirig_root = os.getenv("UNIRIG_ROOT")
    unirig_ready = bool(unirig_root and all((Path(unirig_root) / relative).is_file() for relative in ("launch/inference/generate_skeleton.sh", "launch/inference/generate_skin.sh", "launch/inference/merge.sh")))
    motion_clips = MotionLibrary().clips()
    return {
        "providers": {
            "AUTO": {"available": spar3d["installed"], "reason": None if spar3d["installed"] else spar3d["reason"]},
            "HunyuanMultiviewProvider": {"available": False, "reason": "The multiview worker is not enabled until its official checkout and model weights are installed"},
            "Spar3DProvider": {"available": spar3d["installed"], "reason": None if spar3d["installed"] else spar3d["reason"]},
        },
        "stages": {
            "references": {"available": True, "description": "Validate, crop, alpha-process, normalize and persist reference images"},
            "geometry": {"available": spar3d["installed"], "reason": None if spar3d["installed"] else spar3d["reason"]},
            "textures": {"available": True, "reason": "Runs after a generated mesh and extracts only real embedded textures"},
            "retopology": {"available": bool(blender), "description": "Blender GLB import, triangle decimation and export" if blender else None, "reason": None if blender else "Blender is not installed"},
            "rig": {"available": unirig_ready, "reason": None if unirig_ready else "Configure UNIRIG_ROOT with the official UniRig inference scripts and checkpoint"},
            "motions": {"available": bool(blender and motion_clips), "description": "Blender canonical-bone retarget and bake" if blender and motion_clips else None, "reason": None if blender and motion_clips else "Install and register at least one validated motion library" if blender else "Blender is not installed"},
            "export": {"available": bool(blender), "description": "Blender GLB/FBX export with round-trip validation" if blender else None, "reason": None if blender else "Blender is not installed"},
        },
        "models": models,
    }
