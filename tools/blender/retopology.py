from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy  # type: ignore


def _request_path() -> Path:
    if "--" not in sys.argv or len(sys.argv) <= sys.argv.index("--") + 1:
        raise ValueError("Blender retopology request JSON path is missing")
    return Path(sys.argv[sys.argv.index("--") + 1]).resolve()


def _mesh_objects() -> list:
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def run(request: dict) -> dict:
    mode = str(request.get("mode", "KEEP_SOURCE")).upper()
    if mode not in {"KEEP_SOURCE", "TRIANGLE", "QUAD"}:
        raise ValueError(f"Unsupported retopology mode: {mode}")
    if mode == "QUAD":
        raise RuntimeError("QUAD retopology is disabled until a UV/material-preserving quad remesh path is configured")
    source = Path(request["source_mesh"]).resolve()
    output = Path(request["output_mesh"]).resolve()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = _mesh_objects()
    if not meshes:
        raise RuntimeError("Imported GLB contains no mesh objects")
    source_faces = sum(len(obj.data.polygons) for obj in meshes)
    target_faces = int(request.get("target_faces", source_faces))
    if target_faces <= 0:
        raise ValueError("target_faces must be positive")
    if mode == "TRIANGLE" and source_faces > target_faces:
        ratio = max(0.01, min(1.0, target_faces / source_faces))
        for obj in meshes:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            modifier = obj.modifiers.new(name="CharacterFactoryDecimate", type="DECIMATE")
            modifier.decimate_type = "COLLAPSE"
            modifier.ratio = ratio
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            obj.select_set(False)
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = meshes[0]
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", export_materials="EXPORT", export_animations=True)
    result_meshes = _mesh_objects()
    return {"ok": True, "mode": mode, "source_face_count": source_faces, "output_face_count": sum(len(obj.data.polygons) for obj in result_meshes)}


try:
    response = run(json.loads(_request_path().read_text(encoding="utf-8")))
except (OSError, ValueError, RuntimeError) as error:
    response = {"ok": False, "category": "RETOPOLOGY_ERROR", "error": str(error)}
print("CHARACTER_FACTORY_RESULT=" + json.dumps(response, ensure_ascii=False))
