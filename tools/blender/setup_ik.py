from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy  # type: ignore
from mathutils import Vector  # type: ignore


ALIASES = {
    "head": ("mixamorig:Head", "head"),
    "neck": ("mixamorig:Neck", "neck"),
    "hand_l": ("mixamorig:LeftHand", "hand_l", "lefthand"),
    "hand_r": ("mixamorig:RightHand", "hand_r", "righthand"),
    "lowerarm_l": ("mixamorig:LeftForeArm", "lowerarm_l", "leftforearm"),
    "lowerarm_r": ("mixamorig:RightForeArm", "lowerarm_r", "rightforearm"),
    "foot_l": ("mixamorig:LeftFoot", "foot_l", "leftfoot"),
    "foot_r": ("mixamorig:RightFoot", "foot_r", "rightfoot"),
    "lowerleg_l": ("mixamorig:LeftLeg", "lowerleg_l", "leftleg"),
    "lowerleg_r": ("mixamorig:RightLeg", "lowerleg_r", "rightleg"),
}


def _find_armature() -> object:
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected exactly one armature, found {len(armatures)}")
    return armatures[0]


def _bone(armature: object, key: str) -> str:
    names = {bone.name.lower(): bone.name for bone in armature.data.bones}
    for candidate in ALIASES[key]:
        if candidate.lower() in names:
            return names[candidate.lower()]
    raise RuntimeError(f"Canonical IK bone is missing: {key}")


def _target(name: str, position: Vector) -> object:
    target = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(target)
    target.empty_display_type = "CUBE"
    target.empty_display_size = 0.08
    target.location = position
    target["character_factory_ik_target"] = name
    return target


def _world_head(armature: object, bone_name: str) -> Vector:
    return armature.matrix_world @ armature.pose.bones[bone_name].head


def run(request: dict) -> dict:
    source = Path(request["source_mesh"]).resolve()
    output = Path(request["output_mesh"]).resolve()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    armature = _find_armature()
    targets: list[dict] = []
    constraints: list[dict] = []
    if request.get("foot_ik", True):
        for side in ("l", "r"):
            foot = _bone(armature, f"foot_{side}")
            target = _target(f"ik_target_foot_{side}", _world_head(armature, foot))
            constraint = armature.pose.bones[foot].constraints.new("IK")
            constraint.name = f"CharacterFactoryFootIK_{side}"
            constraint.target = target
            constraint.chain_count = 2
            targets.append({"id": f"foot_{side}", "object": target.name, "bone": foot, "position": list(target.location)})
            constraints.append({"type": "IK", "name": constraint.name, "bone": foot, "chain_count": 2, "target": target.name})
    if request.get("look_ik", True):
        head = _bone(armature, "head")
        target = _target("ik_target_look", _world_head(armature, head) + Vector((0.0, 0.0, 1.0)))
        constraint = armature.pose.bones[head].constraints.new("DAMPED_TRACK")
        constraint.name = "CharacterFactoryLookIK"
        constraint.target = target
        constraint.track_axis = "TRACK_Y"
        targets.append({"id": "look", "object": target.name, "bone": head, "position": list(target.location)})
        constraints.append({"type": "DAMPED_TRACK", "name": constraint.name, "bone": head, "target": target.name, "max_angle_degrees": 70.0})
    if request.get("two_hand_ik"):
        hand = _bone(armature, "hand_l")
        grip = request.get("secondary_grip") or {}
        position = grip.get("position") if isinstance(grip, dict) else None
        target_position = _world_head(armature, hand) if not isinstance(position, (list, tuple)) or len(position) != 3 else Vector((float(position[0]), float(position[1]), float(position[2])))
        target = _target("ik_target_hand_l", target_position)
        constraint = armature.pose.bones[hand].constraints.new("IK")
        constraint.name = "CharacterFactoryTwoHandIK"
        constraint.target = target
        constraint.chain_count = 2
        targets.append({"id": "hand_l", "object": target.name, "bone": hand, "position": list(target.location), "source": "secondary_grip"})
        constraints.append({"type": "IK", "name": constraint.name, "bone": hand, "chain_count": 2, "target": target.name})
    armature["character_factory_ik"] = json.dumps({"targets": targets, "constraints": constraints})
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = armature
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", export_materials="EXPORT", export_animations=True, export_skins=True, export_extras=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Blender did not create IK output")
    return {"ok": True, "targets": targets, "constraints": constraints}


def _request_path() -> Path:
    if "--" not in sys.argv or len(sys.argv) <= sys.argv.index("--") + 1:
        raise ValueError("Blender IK request JSON path is missing")
    return Path(sys.argv[sys.argv.index("--") + 1]).resolve()


try:
    response = run(json.loads(_request_path().read_text(encoding="utf-8")))
except (OSError, ValueError, RuntimeError) as error:
    response = {"ok": False, "category": "IK_ERROR", "error": str(error)}
print("CHARACTER_FACTORY_RESULT=" + json.dumps(response, ensure_ascii=False))
