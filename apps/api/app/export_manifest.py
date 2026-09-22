from __future__ import annotations

from pathlib import Path
from typing import Any

from .schemas import JobManifest
from .storage import atomic_write_json


def build_unit_manifest(job: JobManifest, job_dir: Path, glb_path: Path, fbx_path: Path, roundtrip: dict[str, Any]) -> dict[str, Any]:
    geometry = job.stages.get("geometry")
    final_stage = job.stages.get("rig") or job.stages.get("retopology") or geometry
    validation = (final_stage.result.get("validation") if final_stage else {}) or {}
    textures = job.stages.get("textures")
    rig = job.stages.get("rig")
    motions = job.stages.get("motions")
    equipment = job.stages.get("equipment")
    clothing = job.stages.get("clothing")
    ik = job.stages.get("ik")
    equipment_result = equipment.result if equipment else {}
    exported_glb = roundtrip.get("glb", {}) if isinstance(roundtrip, dict) else {}
    exported_rig = roundtrip.get("rig", {}) if isinstance(roundtrip, dict) else {}
    final_validation = exported_glb or validation
    final_rig_validation = exported_rig or (rig.result.get("validation", {}) if rig else {})
    motion_sources = [
        {
            "clip_id": clip.get("clip_id"),
            "source": clip.get("source"),
            "action": clip.get("action"),
            "license": clip.get("license"),
            "allowed_for_commercial_use": clip.get("allowed_for_commercial_use", False),
        }
        for clip in (motions.result.get("clips", []) if motions else [])
    ]
    return {
        "unit_id": job.job_id,
        "source_references": {view: slot.model_dump(mode="json") for view, slot in job.references.items()},
        "geometry_provider": job.actual_provider or job.requested_provider,
        "geometry_settings": geometry.result.get("settings", {}) if geometry else {},
        "texture_settings": textures.result.get("settings", {}) if textures else {},
        "retopology_settings": job.stages.get("retopology").result if job.stages.get("retopology") else {},
        "vertices": final_validation.get("vertex_count", 0),
        "faces": final_validation.get("face_count", 0),
        "materials": final_validation.get("material_count", 0),
        "textures": textures.result.get("images", []) if textures else [],
        "bones": final_rig_validation.get("joint_count", validation.get("joint_count", 0)),
        "canonical_mapping": final_rig_validation.get("canonical_mapping", {}) or (rig.result.get("validation", {}).get("canonical_mapping", {}) if rig else {}),
        "animations": job.export_actions,
        "motion_sources": motion_sources,
        "equipment": equipment_result.get("assets", []),
        "clothing": clothing.result.get("assets", []) if clothing else [],
        "sockets": equipment_result.get("sockets", []),
        "ik_settings": {
            **(ik.result.get("settings", {}) if ik else {}),
            "targets": ik.result.get("targets", []) if ik else [],
            "constraints": ik.result.get("constraints", []) if ik else [],
        },
        "validation": {"glb_roundtrip": roundtrip, "final_stage": validation},
        "pipeline_version": job.pipeline_version,
        "stage_durations": {name: stage.duration_seconds for name, stage in job.stages.items()},
        "vram_peak_per_stage": {name: stage.result.get("vram", {}).get("peak") if isinstance(stage.result, dict) else None for name, stage in job.stages.items()},
        "warnings": job.warnings,
        "files": {"glb": str(glb_path.relative_to(job_dir)), "fbx": str(fbx_path.relative_to(job_dir)), "manifest": "export/unit.manifest.json"},
    }


def save_unit_manifest(job: JobManifest, job_dir: Path, glb_path: Path, fbx_path: Path, roundtrip: dict[str, Any]) -> Path:
    destination = job_dir / "export" / "unit.manifest.json"
    atomic_write_json(destination, build_unit_manifest(job, job_dir, glb_path, fbx_path, roundtrip))
    return destination
