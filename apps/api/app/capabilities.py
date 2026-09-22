from __future__ import annotations

import shutil
from .blender_discovery import blender_path
from .model_registry import ModelRegistry
from .motion_library import MotionLibrary
from .equipment_library import EquipmentLibrary


def capabilities() -> dict:
    blender = blender_path()
    models = ModelRegistry().status()
    spar3d = next(item for item in models if item["id"] == "spar3d")
    hunyuan = next(item for item in models if item["id"] == "hunyuan3d-2mv")
    hunyuan_single = next(item for item in models if item["id"] == "hunyuan3d-2")
    unirig = next(item for item in models if item["id"] == "unirig")
    motion_clips = MotionLibrary().clips()
    equipment_assets = EquipmentLibrary().catalog().get("assets", [])
    return {
        "providers": {
            "AUTO": {"available": spar3d["installed"] or hunyuan["installed"] or hunyuan_single["installed"], "reason": None if spar3d["installed"] or hunyuan["installed"] or hunyuan_single["installed"] else f"SPAR3D: {spar3d['reason']}; Hunyuan3D-2mv: {hunyuan['reason']}; Hunyuan3D-2: {hunyuan_single['reason']}"},
            "HunyuanMultiviewProvider": {"available": hunyuan["installed"], "reason": None if hunyuan["installed"] else hunyuan["reason"]},
            "HunyuanSingleViewProvider": {"available": hunyuan_single["installed"], "reason": None if hunyuan_single["installed"] else hunyuan_single["reason"]},
            "Spar3DProvider": {"available": spar3d["installed"], "reason": None if spar3d["installed"] else spar3d["reason"]},
        },
        "stages": {
            "references": {"available": True, "description": "Validate, crop, alpha-process, normalize and persist reference images"},
            "geometry": {"available": spar3d["installed"] or hunyuan["installed"] or hunyuan_single["installed"], "reason": None if spar3d["installed"] or hunyuan["installed"] or hunyuan_single["installed"] else f"SPAR3D: {spar3d['reason']}; Hunyuan3D-2mv: {hunyuan['reason']}; Hunyuan3D-2: {hunyuan_single['reason']}"},
            "textures": {"available": True, "reason": "Runs Hunyuan Paint on Hunyuan meshes; otherwise preserves and validates provider textures"},
            "retopology": {"available": bool(blender), "description": "Blender GLB import, triangle decimation and export" if blender else None, "reason": None if blender else "Blender is not installed"},
            "rig": {"available": unirig["installed"], "reason": None if unirig["installed"] else unirig["reason"] or "UniRig runtime is not ready"},
            "motions": {"available": bool(blender and motion_clips), "description": "Blender canonical-bone retarget and bake" if blender and motion_clips else None, "reason": None if blender and motion_clips else "Install and register at least one validated motion library" if blender else "Blender is not installed"},
            "equipment": {"available": bool(blender and equipment_assets), "description": "Blender socket attachment for registered rigid equipment" if blender and equipment_assets else None, "reason": None if blender and equipment_assets else "Register at least one validated equipment asset" if blender else "Blender is not installed"},
            "ik": {"available": bool(blender), "description": "Blender foot, look and two-hand IK constraint setup" if blender else None, "reason": None if blender else "Blender is not installed"},
            "export": {"available": bool(blender), "description": "Blender GLB/FBX export with round-trip validation" if blender else None, "reason": None if blender else "Blender is not installed"},
        },
        "models": models,
    }
