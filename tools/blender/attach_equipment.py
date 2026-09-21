from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy  # type: ignore
from mathutils import Matrix  # type: ignore


SOCKET_BONES = {
    "head_socket": ("head",),
    "back_socket": ("spine_02", "spine2", "chest"),
    "chest_socket": ("chest", "spine_02"),
    "hand_l": ("hand_l", "lefthand", "mixamorig:lefthand"),
    "hand_r": ("hand_r", "righthand", "mixamorig:righthand"),
    "weapon_l": ("hand_l", "lefthand", "mixamorig:lefthand"),
    "weapon_r": ("hand_r", "righthand", "mixamorig:righthand"),
    "hip_l": ("upperleg_l", "leftupleg", "leftthigh"),
    "hip_r": ("upperleg_r", "rightupleg", "rightthigh"),
}


def _key(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def _armature(objects: list[object]) -> object:
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected exactly one target armature, found {len(armatures)}")
    return armatures[0]


def _resolve_bone(armature: object, socket: str) -> str:
    candidates = SOCKET_BONES.get(socket, (socket,))
    by_key = {_key(bone.name): bone.name for bone in armature.data.bones}
    for candidate in candidates:
        if _key(candidate) in by_key:
            return by_key[_key(candidate)]
    raise RuntimeError(f"Socket '{socket}' has no matching target bone")


def _import(path: Path) -> list[object]:
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [obj for obj in bpy.context.scene.objects if obj not in before]


def _socket_transform(asset: dict) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    transform = asset.get("socket_transform", {}) or {}
    return tuple(transform.get("position", (0.0, 0.0, 0.0))), tuple(transform.get("rotation", (0.0, 0.0, 0.0))), tuple(transform.get("scale", (1.0, 1.0, 1.0)))


def run(request: dict) -> dict:
    target_path = Path(request["target_rig"]).resolve()
    output_path = Path(request["output_mesh"]).resolve()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    target_objects = _import(target_path)
    target = _armature(target_objects)
    attached: list[dict[str, str]] = []
    sockets: list[dict] = []
    for asset in request["assets"]:
        asset_path = Path(str(asset["asset_path"])).resolve()
        imported = _import(asset_path)
        meshes = [obj for obj in imported if obj.type == "MESH"]
        if not meshes:
            raise RuntimeError(f"Equipment asset contains no mesh: {asset['id']}")
        socket_id = str(asset.get("primary_socket") or asset.get("slot") or "hand_r")
        bone_name = _resolve_bone(target, socket_id)
        socket_name = f"socket_{asset['id']}_{socket_id}"
        socket = bpy.data.objects.new(socket_name, None)
        bpy.context.collection.objects.link(socket)
        socket.parent = target
        socket.parent_type = "BONE"
        socket.parent_bone = bone_name
        position, rotation, scale = _socket_transform(asset)
        socket.location = position
        socket.rotation_mode = "XYZ"
        socket.rotation_euler = rotation
        socket.scale = scale
        socket["character_factory_socket_id"] = socket_id
        socket["character_factory_asset_id"] = asset["id"]
        for mesh in meshes:
            mesh.parent = socket
            mesh.matrix_parent_inverse = Matrix.Identity(4)
            mesh.location = (0.0, 0.0, 0.0)
            mesh.rotation_mode = "XYZ"
            mesh.rotation_euler = (0.0, 0.0, 0.0)
        attached.append({"id": str(asset["id"]), "socket": socket_id, "bone": bone_name})
        sockets.append({"id": socket_id, "object": socket_name, "parentBone": bone_name, "position": list(position), "rotation": list(rotation), "scale": list(scale)})
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = target
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output_path), export_format="GLB", export_materials="EXPORT", export_animations=True, export_skins=True, export_extras=True)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Blender did not create equipment output")
    return {"ok": True, "attached": attached, "sockets": sockets}


def _request_path() -> Path:
    if "--" not in sys.argv or len(sys.argv) <= sys.argv.index("--") + 1:
        raise ValueError("Blender equipment request JSON path is missing")
    return Path(sys.argv[sys.argv.index("--") + 1]).resolve()


try:
    response = run(json.loads(_request_path().read_text(encoding="utf-8")))
except (OSError, ValueError, RuntimeError) as error:
    response = {"ok": False, "category": "EQUIPMENT_ERROR", "error": str(error)}
print("CHARACTER_FACTORY_RESULT=" + json.dumps(response, ensure_ascii=False))
