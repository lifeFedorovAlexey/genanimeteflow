from __future__ import annotations

from pathlib import Path
from typing import Any

from .schemas import JobManifest, StageName, StageStatus


REQUIRED_STAGES = (
    StageName.REFERENCES,
    StageName.GEOMETRY,
    StageName.TEXTURES,
    StageName.RETOPOLOGY,
    StageName.RIG,
    StageName.MOTIONS,
    StageName.EXPORT,
)


def _check(checks: list[dict[str, Any]], check_id: str, label: str, passed: bool, detail: str) -> None:
    checks.append({"id": check_id, "label": label, "passed": passed, "detail": detail})


def _safe_job_file(job_dir: Path, relative_path: object) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path:
        return None
    candidate = (job_dir / relative_path).resolve()
    if job_dir.resolve() not in candidate.parents:
        return None
    return candidate


def validate_job(manifest: JobManifest, job_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for stage in REQUIRED_STAGES:
        record = manifest.stages.get(stage.value)
        _check(checks, f"stage:{stage.value}", f"{stage.value} stage", record is not None and record.status is StageStatus.READY, record.status.value if record else "missing")

    front = manifest.references.get("front")
    front_file = _safe_job_file(job_dir, front.original_path if front else None)
    front_exists = bool(front_file and front_file.is_file())
    _check(checks, "reference:front", "Front reference preserved", front_exists, front.original_path or "missing")

    export = manifest.stages.get(StageName.EXPORT.value)
    export_result = export.result if export else {}
    glb_path = export_result.get("glb_path")
    fbx_path = export_result.get("fbx_path")
    manifest_path = export_result.get("manifest_path")
    glb_file = _safe_job_file(job_dir, glb_path)
    fbx_file = _safe_job_file(job_dir, fbx_path)
    export_manifest_file = _safe_job_file(job_dir, manifest_path)
    glb_exists = bool(glb_file and glb_file.is_file())
    fbx_exists = bool(fbx_file and fbx_file.is_file())
    export_manifest_exists = bool(export_manifest_file and export_manifest_file.is_file())
    _check(checks, "export:glb", "Final GLB exists", glb_exists, str(glb_path or "missing"))
    _check(checks, "export:fbx", "Final FBX exists", fbx_exists, str(fbx_path or "missing"))
    _check(checks, "export:manifest", "Export manifest exists", export_manifest_exists, str(manifest_path or "missing"))

    roundtrip = export_result.get("roundtrip", {}) if isinstance(export_result, dict) else {}
    glb_validation = roundtrip.get("glb", {}) if isinstance(roundtrip, dict) else {}
    rig_validation = roundtrip.get("rig", {}) if isinstance(roundtrip, dict) else {}
    selected_actions = export_result.get("selected_actions", []) if isinstance(export_result, dict) else []
    animation_count = int(roundtrip.get("animation_count", glb_validation.get("animation_count", 0)) or 0) if isinstance(roundtrip, dict) else 0
    texture_count = int(glb_validation.get("texture_count", 0) or 0) if isinstance(glb_validation, dict) else 0
    joint_count = int(rig_validation.get("joint_count", 0) or 0) if isinstance(rig_validation, dict) else 0
    _check(checks, "asset:validated", "Final GLB validation", bool(glb_validation.get("valid")), "; ".join(glb_validation.get("errors", [])) or "valid")
    _check(checks, "asset:textures", "Embedded textures", texture_count > 0, f"{texture_count} texture(s)")
    _check(checks, "asset:skin", "Skinned skeleton", bool(glb_validation.get("skin_count", 0)) and joint_count > 0, f"{joint_count} joint(s)")
    _check(checks, "asset:animations", "Selected animations", bool(selected_actions) and animation_count >= len(selected_actions), f"{animation_count} clip(s), {len(selected_actions)} selected")

    if manifest.equipment_assets:
        equipment = manifest.stages.get(StageName.EQUIPMENT.value)
        _check(checks, "equipment:attached", "Selected equipment attached", equipment is not None and equipment.status is StageStatus.READY, ", ".join(manifest.equipment_assets))
    if manifest.clothing_assets:
        clothing = manifest.stages.get(StageName.CLOTHING.value)
        _check(checks, "clothing:transferred", "Selected clothing transferred", clothing is not None and clothing.status is StageStatus.READY, ", ".join(manifest.clothing_assets))
    if manifest.equipment_assets:
        ik = manifest.stages.get(StageName.IK.value)
        ik_result = ik.result if ik else {}
        target_count = len(ik_result.get("targets", [])) if isinstance(ik_result, dict) else 0
        constraint_count = len(ik_result.get("constraints", [])) if isinstance(ik_result, dict) else 0
        _check(checks, "ik:targets", "Equipment IK targets", ik is not None and ik.status is StageStatus.READY and target_count > 0 and constraint_count > 0, f"{target_count} target(s), {constraint_count} constraint(s)")

    passed = all(bool(item["passed"]) for item in checks)
    return {
        "job_id": manifest.job_id,
        "valid": passed,
        "checks": checks,
        "metrics": {
            "vertices": int(glb_validation.get("vertex_count", 0) or 0) if isinstance(glb_validation, dict) else 0,
            "textures": texture_count,
            "bones": joint_count,
            "animations": animation_count,
            "selected_actions": len(selected_actions),
        },
    }
