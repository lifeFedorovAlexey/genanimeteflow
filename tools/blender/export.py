from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy  # type: ignore


def _request_path() -> Path:
    if "--" not in sys.argv or len(sys.argv) <= sys.argv.index("--") + 1:
        raise ValueError("Blender export request JSON path is missing")
    return Path(sys.argv[sys.argv.index("--") + 1]).resolve()


def _filter_actions(selected: list[str]) -> list[str]:
    available = [action.name for action in bpy.data.actions]
    missing = [name for name in selected if name not in available]
    if missing:
        raise RuntimeError("Requested animation actions are missing: " + ", ".join(missing))
    if selected:
        for action in list(bpy.data.actions):
            if action.name not in selected:
                bpy.data.actions.remove(action, do_unlink=True)
    return available


def _roundtrip(glb_path: Path) -> dict[str, int]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    mesh_count = len([obj for obj in bpy.context.scene.objects if obj.type == "MESH"])
    armature_count = len([obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"])
    action_count = len(bpy.data.actions)
    if mesh_count == 0:
        raise RuntimeError("Exported GLB roundtrip contains no mesh objects")
    return {"mesh_count": mesh_count, "armature_count": armature_count, "animation_count": action_count}


def run(request: dict) -> dict:
    source = Path(request["source_mesh"]).resolve()
    glb = Path(request["glb_output"]).resolve()
    fbx = Path(request["fbx_output"]).resolve()
    selected = [str(name) for name in request.get("selected_actions", [])]
    if not source.is_file():
        raise RuntimeError(f"Export source does not exist: {source}")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    available = _filter_actions(selected)
    glb.parent.mkdir(parents=True, exist_ok=True)
    fbx.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", export_materials="EXPORT", export_animations=bool(selected))
    if not glb.is_file() or glb.stat().st_size == 0:
        raise RuntimeError("GLB exporter did not create a non-empty file")
    bpy.ops.export_scene.fbx(filepath=str(fbx), add_leaf_bones=False, bake_anim=bool(selected))
    if not fbx.is_file() or fbx.stat().st_size == 0:
        raise RuntimeError("FBX exporter did not create a non-empty file")
    roundtrip = _roundtrip(glb)
    if selected and roundtrip["animation_count"] == 0:
        raise RuntimeError("Exported GLB roundtrip contains no selected animations")
    return {"ok": True, "available_actions": available, "selected_actions": selected, "roundtrip": roundtrip}


try:
    response = run(json.loads(_request_path().read_text(encoding="utf-8")))
except (OSError, ValueError, RuntimeError) as error:
    response = {"ok": False, "category": "EXPORT_ERROR", "error": str(error)}
print("CHARACTER_FACTORY_RESULT=" + json.dumps(response, ensure_ascii=False))
