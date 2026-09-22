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


def _ensure_uv(obj) -> bool:
    if obj.data.uv_layers:
        return False
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.03)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)
    return True


def run(request: dict) -> dict:
    mode = str(request.get("mode", "KEEP_SOURCE")).upper()
    if mode not in {"KEEP_SOURCE", "TRIANGLE", "QUAD"}:
        raise ValueError(f"Unsupported retopology mode: {mode}")
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
    uv_generated = False
    if mode == "QUAD":
        # Blender's built-in Quadriflow is an actual quad remesher. Process
        # each imported mesh separately so materials and object boundaries do
        # not get silently merged. preserve_attributes keeps material indices,
        # vertex groups and UV layers when Blender can transfer them.
        per_object_target = max(4, target_faces // max(1, len(meshes)))
        for obj in meshes:
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            quad_result = bpy.ops.object.quadriflow_remesh(
                target_faces=per_object_target,
                preserve_attributes=True,
                use_preserve_boundary=True,
                smooth_normals=True,
            )
            if "FINISHED" not in quad_result:
                # Generated meshes can contain open/non-manifold seams. Use
                # Blender's real voxel remesh as a repair pass, then retry
                # Quadriflow; never report QUAD success when the operator was
                # cancelled and the source topology remained untouched.
                maximum_dimension = max(obj.dimensions) or 1.0
                voxel_size = maximum_dimension / max(12.0, min(180.0, per_object_target ** (1.0 / 3.0) * 2.0))
                obj.data.remesh_voxel_size = max(0.001, min(0.2, voxel_size))
                obj.data.use_remesh_fix_poles = True
                obj.data.use_remesh_preserve_volume = True
                bpy.ops.object.voxel_remesh()
                quad_result = bpy.ops.object.quadriflow_remesh(
                    target_faces=per_object_target,
                    preserve_attributes=False,
                    use_preserve_boundary=True,
                    smooth_normals=True,
                )
            if "FINISHED" not in quad_result:
                raise RuntimeError(f"Blender Quadriflow could not remesh object '{obj.name}'")
            uv_generated = _ensure_uv(obj) or uv_generated
            obj.select_set(False)
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = meshes[0]
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", export_materials="EXPORT", export_animations=True)
    result_meshes = _mesh_objects()
    return {"ok": True, "mode": mode, "source_face_count": source_faces, "output_face_count": sum(len(obj.data.polygons) for obj in result_meshes), "uv_generated": uv_generated}


try:
    response = run(json.loads(_request_path().read_text(encoding="utf-8")))
except (OSError, ValueError, RuntimeError) as error:
    response = {"ok": False, "category": "RETOPOLOGY_ERROR", "error": str(error)}
print("CHARACTER_FACTORY_RESULT=" + json.dumps(response, ensure_ascii=False))
