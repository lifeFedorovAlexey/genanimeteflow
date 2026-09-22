from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy  # type: ignore
from mathutils import kdtree  # type: ignore


def _import(path: Path) -> list[object]:
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [obj for obj in bpy.context.scene.objects if obj not in before]


def _armature(objects: list[object]) -> object:
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected one target armature, found {len(armatures)}")
    return armatures[0]


def _body_weights(body: object, index: int, names: set[str]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for group in body.vertex_groups:
        if group.name not in names:
            continue
        try:
            value = group.weight(index)
        except RuntimeError:
            continue
        if value > 0:
            weights[group.name] = value
    total = sum(weights.values())
    return {name: value / total for name, value in weights.items()} if total > 0 else {}


def run(request: dict) -> dict:
    target_path = Path(request["target_rig"]).resolve()
    output_path = Path(request["output_mesh"]).resolve()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    target_objects = _import(target_path)
    armature = _armature(target_objects)
    body_meshes = [obj for obj in target_objects if obj.type == "MESH" and any(mod.type == "ARMATURE" for mod in obj.modifiers)]
    if not body_meshes:
        raise RuntimeError("Target rig contains no skinned body mesh")
    bone_names = {bone.name for bone in armature.data.bones}
    points: list[tuple[float, int]] = []
    weights: list[dict[str, float]] = []
    tree = kdtree.KDTree(sum(len(mesh.data.vertices) for mesh in body_meshes))
    cursor = 0
    for body in body_meshes:
        for vertex in body.data.vertices:
            world = body.matrix_world @ vertex.co
            tree.insert(world, cursor)
            weights.append(_body_weights(body, vertex.index, bone_names))
            cursor += 1
    tree.balance()
    imported_clothing: list[dict] = []
    for asset in request["assets"]:
        source_objects = _import(Path(str(asset["asset_path"])).resolve())
        meshes = [obj for obj in source_objects if obj.type == "MESH"]
        if not meshes:
            raise RuntimeError(f"Clothing asset contains no mesh: {asset['id']}")
        for mesh in meshes:
            mesh.name = f"Clothing_{asset['id']}_{mesh.name}"
            for modifier in list(mesh.modifiers):
                mesh.modifiers.remove(modifier)
            groups = {name: mesh.vertex_groups.new(name=name) for name in bone_names}
            nearest_distances: list[float] = []
            for vertex in mesh.data.vertices:
                world = mesh.matrix_world @ vertex.co
                _, nearest_index, distance = tree.find(world)
                nearest_distances.append(float(distance))
                for bone, value in weights[nearest_index].items():
                    groups[bone].add([vertex.index], value, "REPLACE")
            armature_modifier = mesh.modifiers.new(name="CharacterFactoryClothingArmature", type="ARMATURE")
            armature_modifier.object = armature
            mesh["character_factory_clothing_asset"] = asset["id"]
            clip_threshold = 0.001
            clipped = sum(distance <= clip_threshold for distance in nearest_distances)
            imported_clothing.append({"id": asset["id"], "mesh": mesh.name, "vertex_count": len(mesh.data.vertices), "nearest_surface_distance": {"min": min(nearest_distances), "mean": sum(nearest_distances) / len(nearest_distances)}, "clipping_vertices": clipped, "clipping_ratio": clipped / len(nearest_distances)})
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = armature
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output_path), export_format="GLB", export_materials="EXPORT", export_animations=True, export_skins=True, export_extras=True)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Blender did not create clothing output")
    return {"ok": True, "transfer": imported_clothing, "clipping": imported_clothing}


def _request_path() -> Path:
    if "--" not in sys.argv or len(sys.argv) <= sys.argv.index("--") + 1:
        raise ValueError("Blender clothing request JSON path is missing")
    return Path(sys.argv[sys.argv.index("--") + 1]).resolve()


try:
    response = run(json.loads(_request_path().read_text(encoding="utf-8")))
except (OSError, ValueError, RuntimeError) as error:
    response = {"ok": False, "category": "CLOTHING_ERROR", "error": str(error)}
print("CHARACTER_FACTORY_RESULT=" + json.dumps(response, ensure_ascii=False))
