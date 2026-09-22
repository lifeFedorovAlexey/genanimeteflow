from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy  # type: ignore


ALIASES: dict[str, tuple[str, ...]] = {
    "root": ("root", "armature", "origin"),
    "hips": ("hips", "hip", "pelvis", "mixamorig:hips", "def-hips"),
    "spine_01": ("spine_01", "spine", "spine1", "mixamorig:spine", "def-spine.001"),
    "spine_02": ("spine_02", "spine2", "chest", "mixamorig:spine1", "def-spine.002"),
    "chest": ("chest", "upperchest", "spine3", "mixamorig:spine2", "def-spine.003"),
    "neck": ("neck", "mixamorig:neck", "def-neck"),
    "head": ("head", "mixamorig:head", "def-head"),
    "clavicle_l": ("clavicle_l", "leftclavicle", "l_clavicle", "mixamorig:leftshoulder", "def-shoulder.l"),
    "upperarm_l": ("upperarm_l", "leftupperarm", "l_upperarm", "mixamorig:leftarm", "def-upper_arm.l"),
    "lowerarm_l": ("lowerarm_l", "leftlowerarm", "l_lowerarm", "mixamorig:leftforearm", "def-forearm.l"),
    "hand_l": ("hand_l", "lefthand", "l_hand", "mixamorig:lefthand", "def-hand.l"),
    "clavicle_r": ("clavicle_r", "rightclavicle", "r_clavicle", "mixamorig:rightshoulder", "def-shoulder.r"),
    "upperarm_r": ("upperarm_r", "rightupperarm", "r_upperarm", "mixamorig:rightarm", "def-upper_arm.r"),
    "lowerarm_r": ("lowerarm_r", "rightlowerarm", "r_lowerarm", "mixamorig:rightforearm", "def-forearm.r"),
    "hand_r": ("hand_r", "righthand", "r_hand", "mixamorig:righthand", "def-hand.r"),
    "upperleg_l": ("upperleg_l", "leftupleg", "leftthigh", "thigh_l", "l_thigh", "mixamorig:leftupleg", "def-thigh.l"),
    "lowerleg_l": ("lowerleg_l", "leftleg", "leftcalf", "calf_l", "l_calf", "mixamorig:leftleg", "def-shin.l"),
    "foot_l": ("foot_l", "leftfoot", "foot_l", "l_foot", "mixamorig:leftfoot", "def-foot.l"),
    "upperleg_r": ("upperleg_r", "rightupleg", "rightthigh", "thigh_r", "r_thigh", "mixamorig:rightupleg", "def-thigh.r"),
    "lowerleg_r": ("lowerleg_r", "rightleg", "rightcalf", "calf_r", "r_calf", "mixamorig:rightleg", "def-shin.r"),
    "foot_r": ("foot_r", "rightfoot", "foot_r", "r_foot", "mixamorig:rightfoot", "def-foot.r"),
}


def _key(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def _mapping(source: object, target: object) -> dict[str, tuple[str, str]]:
    source_bones = { _key(bone.name): bone.name for bone in source.data.bones }
    target_bones = { _key(bone.name): bone.name for bone in target.data.bones }
    mapping: dict[str, tuple[str, str]] = {}
    for canonical, aliases in ALIASES.items():
        source_name = next((source_bones[_key(alias)] for alias in aliases if _key(alias) in source_bones), None)
        target_name = next((target_bones[_key(alias)] for alias in aliases if _key(alias) in target_bones), None)
        if source_name and target_name:
            mapping[canonical] = (source_name, target_name)
    required = {"hips", "spine_01", "upperarm_l", "upperarm_r", "upperleg_l", "upperleg_r"}
    missing = sorted(required - mapping.keys())
    if missing:
        raise RuntimeError("Canonical retarget mapping is missing: " + ", ".join(missing))
    return mapping


def _detect_root_motion(action: object, mapping: dict[str, tuple[str, str]]) -> bool:
    """Detect meaningful translation on the source root/hips track."""
    source_names = {name.lower() for name in (mapping.get("root", (None, None))[0], mapping.get("hips", (None, None))[0]) if name}
    frame_start = float(action.frame_range[0])
    frame_end = float(action.frame_range[1])
    displacement = 0.0
    for curve in action.fcurves:
        if "location" not in curve.data_path.lower():
            continue
        path = curve.data_path.lower()
        if "pose.bones[" in path and not any(name in path for name in source_names):
            continue
        displacement += abs(float(curve.evaluate(frame_end)) - float(curve.evaluate(frame_start)))
    return displacement > 0.02


def _armature(objects: list[object], role: str) -> object:
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected exactly one {role} armature, found {len(armatures)}")
    return armatures[0]


def _import(path: Path) -> list[object]:
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [obj for obj in bpy.context.scene.objects if obj not in before]


def _roundtrip(path: Path, action_name: str) -> dict[str, int | bool]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    mesh_count = len([obj for obj in bpy.context.scene.objects if obj.type == "MESH"])
    armature_count = len([obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"])
    action_names = {action.name for action in bpy.data.actions}
    if not mesh_count or armature_count != 1:
        raise RuntimeError("Normalized GLB roundtrip does not contain one mesh and one armature")
    if action_name not in action_names:
        raise RuntimeError(f"Normalized GLB roundtrip is missing action: {action_name}")
    return {"mesh_count": mesh_count, "armature_count": armature_count, "animation_count": len(action_names), "selected_action_present": True}


def run(request: dict) -> dict:
    source_path = Path(request["source_motion"]).resolve()
    target_path = Path(request["target_rig"]).resolve()
    output_path = Path(request["output_mesh"]).resolve()
    action_name = str(request["action"])
    if not source_path.is_file() or not target_path.is_file():
        raise RuntimeError("Source motion and target rig files must exist")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    target_objects = _import(target_path)
    target = _armature(target_objects, "target")
    source_objects = _import(source_path)
    source = _armature(source_objects, "source")
    action = bpy.data.actions.get(action_name)
    if action is None:
        raise RuntimeError(f"Motion action does not exist: {action_name}")
    mapping = _mapping(source, target)
    detected_root_motion = _detect_root_motion(action, mapping)
    source.animation_data_create()
    source.animation_data.action = action
    target.animation_data_create()
    baked_action = bpy.data.actions.new(name=f"normalized_{action_name}")
    target.animation_data.action = baked_action
    for _, (source_name, target_name) in mapping.items():
        constraint = target.pose.bones[target_name].constraints.new("COPY_ROTATION")
        constraint.name = f"retarget_{target_name}"
        constraint.target = source
        constraint.subtarget = source_name
        constraint.owner_space = "POSE"
        constraint.target_space = "POSE"
        constraint.mix_mode = "REPLACE"
    frame_start = int(action.frame_range[0])
    frame_end = int(action.frame_range[1])
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.nla.bake(frame_start=frame_start, frame_end=frame_end, step=1, only_selected=False, visual_keying=True, clear_constraints=True, use_current_action=True, bake_types={"POSE"})
    bpy.ops.object.mode_set(mode="OBJECT")
    baked_action_name = baked_action.name
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    for obj in source_objects:
        if obj != source:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.objects.remove(source, do_unlink=True)
    for candidate in list(bpy.data.actions):
        if candidate != baked_action and candidate.users == 0:
            bpy.data.actions.remove(candidate)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output_path), export_format="GLB", export_animations=True, export_skins=True, export_materials="EXPORT")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Blender did not create normalized motion output")
    roundtrip = _roundtrip(output_path, baked_action_name)
    return {"ok": True, "action": action_name, "normalized_action": baked_action_name, "root_motion": detected_root_motion, "canonical_mapping": {key: {"source": value[0], "target": value[1]} for key, value in mapping.items()}, "frame_start": frame_start, "frame_end": frame_end, "roundtrip": roundtrip}


def _request_path() -> Path:
    if "--" not in sys.argv or len(sys.argv) <= sys.argv.index("--") + 1:
        raise ValueError("Blender normalization request JSON path is missing")
    return Path(sys.argv[sys.argv.index("--") + 1]).resolve()


try:
    response = run(json.loads(_request_path().read_text(encoding="utf-8")))
except (OSError, ValueError, RuntimeError) as error:
    response = {"ok": False, "category": "NORMALIZATION_ERROR", "error": str(error)}
print("CHARACTER_FACTORY_RESULT=" + json.dumps(response, ensure_ascii=False))
