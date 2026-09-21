from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .glb import GlbReader, validate_glb


CANONICAL_ALIASES: dict[str, tuple[str, ...]] = {
    "root": ("root", "armature", "origin"),
    "hips": ("hips", "hip", "pelvis", "mixamorig:hips"),
    "spine_01": ("spine_01", "spine", "spine1", "mixamorig:spine"),
    "spine_02": ("spine_02", "spine2", "chest", "mixamorig:spine1"),
    "chest": ("chest", "upperchest", "spine3", "mixamorig:spine2"),
    "neck": ("neck", "mixamorig:neck"),
    "head": ("head", "mixamorig:head"),
    "clavicle_l": ("clavicle_l", "leftclavicle", "l_clavicle", "mixamorig:leftshoulder"),
    "upperarm_l": ("upperarm_l", "leftupperarm", "l_upperarm", "mixamorig:leftarm"),
    "lowerarm_l": ("lowerarm_l", "leftlowerarm", "l_lowerarm", "mixamorig:leftforearm"),
    "hand_l": ("hand_l", "lefthand", "l_hand", "mixamorig:lefthand"),
    "clavicle_r": ("clavicle_r", "rightclavicle", "r_clavicle", "mixamorig:rightshoulder"),
    "upperarm_r": ("upperarm_r", "rightupperarm", "r_upperarm", "mixamorig:rightarm"),
    "lowerarm_r": ("lowerarm_r", "rightlowerarm", "r_lowerarm", "mixamorig:rightforearm"),
    "hand_r": ("hand_r", "righthand", "r_hand", "mixamorig:righthand"),
    "upperleg_l": ("upperleg_l", "leftupleg", "leftthigh", "l_thigh", "mixamorig:leftupleg"),
    "lowerleg_l": ("lowerleg_l", "leftleg", "leftcalf", "l_calf", "mixamorig:leftleg"),
    "foot_l": ("foot_l", "leftfoot", "l_foot", "mixamorig:leftfoot"),
    "toe_l": ("toe_l", "lefttoe", "l_toe", "mixamorig:lefttoebase"),
    "upperleg_r": ("upperleg_r", "rightupleg", "rightthigh", "r_thigh", "mixamorig:rightupleg"),
    "lowerleg_r": ("lowerleg_r", "rightleg", "rightcalf", "r_calf", "mixamorig:rightleg"),
    "foot_r": ("foot_r", "rightfoot", "r_foot", "mixamorig:rightfoot"),
    "toe_r": ("toe_r", "righttoe", "r_toe", "mixamorig:righttoebase"),
}


@dataclass
class RigValidationReport:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    joint_count: int = 0
    influenced_vertex_count: int = 0
    canonical_mapping: dict[str, str] = field(default_factory=dict)
    extra_bones: list[str] = field(default_factory=list)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def canonical_mapping(names: list[str]) -> tuple[dict[str, str], list[str]]:
    by_key = {_key(name): name for name in names}
    mapping: dict[str, str] = {}
    for canonical, aliases in CANONICAL_ALIASES.items():
        for alias in aliases:
            match = by_key.get(_key(alias))
            if match:
                mapping[canonical] = match
                break
    extras = [name for name in names if name not in mapping.values()]
    return mapping, extras


def validate_rigged_glb(path: Path, require_canonical: bool = False) -> RigValidationReport:
    base = validate_glb(path, require_skeleton=True)
    report = RigValidationReport(valid=base.valid, errors=list(base.errors), warnings=list(base.warnings))
    if not path.is_file():
        return report
    reader = GlbReader(path)
    try:
        reader.read()
    except (OSError, ValueError, UnicodeDecodeError):
        return report
    nodes = reader.document.get("nodes", [])
    skins = reader.document.get("skins", [])
    if not skins:
        report.errors.append("No skins are present")
        report.valid = False
        return report
    skin = skins[0]
    joint_indices = skin.get("joints", [])
    report.joint_count = len(joint_indices)
    if not joint_indices:
        report.errors.append("Skin has no joints")
    if any(not isinstance(index, int) or index < 0 or index >= len(nodes) for index in joint_indices):
        report.errors.append("Skin contains an out-of-range joint node")
    names = [str(nodes[index].get("name", f"joint_{index}")) for index in joint_indices if isinstance(index, int) and 0 <= index < len(nodes)]
    report.canonical_mapping, report.extra_bones = canonical_mapping(names)
    if require_canonical:
        missing = [name for name in CANONICAL_ALIASES if name not in report.canonical_mapping]
        if missing:
            report.errors.append("Missing canonical bones: " + ", ".join(missing))
    for mesh in reader.document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            attributes = primitive.get("attributes", {})
            if "JOINTS_0" not in attributes or "WEIGHTS_0" not in attributes:
                report.errors.append("Skinned primitive is missing JOINTS_0 or WEIGHTS_0")
                continue
            try:
                joints = reader.accessor_values(int(attributes["JOINTS_0"]))
                weights = reader.accessor_values(int(attributes["WEIGHTS_0"]))
            except (ValueError, IndexError) as error:
                report.errors.append(str(error))
                continue
            if len(joints) != len(weights):
                report.errors.append("JOINTS_0 and WEIGHTS_0 counts differ")
                continue
            report.influenced_vertex_count += len(joints)
            for joint_values, weight_values in zip(joints, weights):
                if any(int(value) >= report.joint_count for value in joint_values):
                    report.errors.append("A vertex references a joint outside the skin")
                numeric_weights = [float(value) for value in weight_values]
                if any(not math.isfinite(value) or value < 0 for value in numeric_weights):
                    report.errors.append("Skin weights contain invalid values")
                total = sum(numeric_weights)
                if total <= 0 or abs(total - 1.0) > 0.1:
                    report.errors.append("Skin weights are not normalized")
    report.valid = not report.errors and report.joint_count > 0 and report.influenced_vertex_count > 0
    return report
