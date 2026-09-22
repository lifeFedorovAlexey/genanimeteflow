from __future__ import annotations

from pathlib import Path
from typing import Any

from .animation_graph import inspect_graph, motion_clips_from_records
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


def _graph_acceptance(records: object) -> dict[str, tuple[bool, str]]:
    if not isinstance(records, list):
        return {"graph:states": (False, "normalized motion records are missing")}
    clips = motion_clips_from_records(records)
    if not clips:
        return {"graph:states": (False, "normalized motion records are empty")}
    report = inspect_graph(clips)
    return {
        "graph:states": (not report["missing_states"], f"{report['clip_count']} clips; missing playable states: {', '.join(report['missing_states']) or 'none'}"),
        "graph:transitions": (report["transition"] == "idle->walk" and report["transition_duration"] > 0, f"{report['transition'] or 'none'} / {report['transition_duration']:.3f}s"),
        "graph:combat": (bool(report["attack_action"]), report["attack_action"] or "no compatible attack clip"),
        "graph:layers": (report["layer_count"] > 0, f"{report['layer_count']} layer(s)"),
        "graph:root-motion": (report["root_motion_mode"] in {"apply", "in_place"}, report["root_motion_mode"]),
    }


def validate_job(manifest: JobManifest, job_dir: Path, require_full_acceptance: bool = False) -> dict[str, Any]:
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

    motion_result = manifest.stages.get(StageName.MOTIONS.value).result if manifest.stages.get(StageName.MOTIONS.value) else {}
    for check_id, (passed, detail) in _graph_acceptance(motion_result.get("clips", []) if isinstance(motion_result, dict) else None).items():
        _check(checks, check_id, check_id.removeprefix("graph:").replace("-", " ").title(), passed, detail)

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

    if require_full_acceptance:
        processed_views = {
            slot.view
            for slot in manifest.references.values()
            if slot.processed_path and slot.quality and slot.quality.get("level") != "ERROR"
        }
        _check(checks, "full:four-views", "Four validated reference views", processed_views == {"front", "left", "back", "right"}, ", ".join(sorted(processed_views)) or "none")

        geometry_result = manifest.stages.get(StageName.GEOMETRY.value).result if manifest.stages.get(StageName.GEOMETRY.value) else {}
        provider_views = set(geometry_result.get("provider_views", [])) if isinstance(geometry_result, dict) else set()
        _check(checks, "full:multiview", "Official multiview geometry", manifest.actual_provider == "HunyuanMultiviewProvider" and provider_views == {"front", "left", "back", "right"}, f"{manifest.actual_provider or 'unknown'} / {', '.join(sorted(provider_views)) or 'no provider views'}")

        reference_result = manifest.stages.get(StageName.REFERENCES.value).result if manifest.stages.get(StageName.REFERENCES.value) else {}
        consistency = reference_result.get("view_consistency", {}) if isinstance(reference_result, dict) else {}
        _check(checks, "full:view-consistency", "DINOv3 view consistency", consistency.get("level") == "GOOD", consistency.get("level", "not measured"))

        selected_assets = {asset.lower() for asset in manifest.equipment_assets}
        _check(checks, "full:sword", "Sword equipment path", any("sword" in asset for asset in selected_assets), ", ".join(sorted(selected_assets)) or "no sword selected")
        _check(checks, "full:rifle", "Rifle equipment path", any("rifle" in asset for asset in selected_assets), ", ".join(sorted(selected_assets)) or "no rifle selected")
        clothing = manifest.stages.get(StageName.CLOTHING.value)
        _check(checks, "full:clothing", "Clothing transfer path", bool(manifest.clothing_assets) and clothing is not None and clothing.status is StageStatus.READY, ", ".join(manifest.clothing_assets) or "no clothing selected")
        ik = manifest.stages.get(StageName.IK.value)
        ik_result = ik.result if ik else {}
        _check(checks, "full:ik", "IK validation path", ik is not None and ik.status is StageStatus.READY and bool(ik_result.get("targets")) and bool(ik_result.get("constraints")), "ready" if ik and ik.status is StageStatus.READY else "not ready")

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
