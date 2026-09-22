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


def _activate_actions(selected: list[str]) -> None:
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Export requires exactly one target armature, found {len(armatures)}")
    if not selected:
        return
    target = armatures[0]
    target.animation_data_create()
    target.animation_data.action = None
    for track in list(target.animation_data.nla_tracks):
        target.animation_data.nla_tracks.remove(track)
    for action_name in selected:
        action = bpy.data.actions[action_name]
        track = target.animation_data.nla_tracks.new()
        track.name = action_name
        frame_start = int(action.frame_range[0])
        strip = track.strips.new(action_name, frame_start, action)
        strip.action_frame_start = action.frame_range[0]
        strip.action_frame_end = action.frame_range[1]
        strip.frame_start = action.frame_range[0]
        strip.frame_end = action.frame_range[1]
    bpy.context.view_layer.objects.active = target
    target.select_set(True)


def _import_motion_actions(paths: list[str]) -> None:
    """Import baked actions from normalized GLBs onto the base character.

    The motion stage intentionally writes one validated GLB per clip. Export
    is the assembly boundary: keep the base mesh/materials from the rigged
    asset, retain only the action datablocks from each selected clip, and
    remove the temporary imported motion objects before exporting.
    """
    for raw_path in paths:
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise RuntimeError(f"Normalized motion source does not exist: {path}")
        before_objects = set(bpy.context.scene.objects)
        before_actions = set(bpy.data.actions)
        bpy.ops.import_scene.gltf(filepath=str(path))
        imported_actions = [action for action in bpy.data.actions if action not in before_actions]
        if not imported_actions:
            raise RuntimeError(f"Normalized motion source contains no action: {path.name}")
        for action in imported_actions:
            action.use_fake_user = True
        for obj in [obj for obj in bpy.context.scene.objects if obj not in before_objects]:
            bpy.data.objects.remove(obj, do_unlink=True)


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
    _import_motion_actions([str(path) for path in request.get("motion_meshes", [])])
    available = _filter_actions(selected)
    _activate_actions(selected)
    glb.parent.mkdir(parents=True, exist_ok=True)
    fbx.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", export_materials="EXPORT", export_animations=bool(selected), export_animation_mode="NLA_TRACKS")
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
