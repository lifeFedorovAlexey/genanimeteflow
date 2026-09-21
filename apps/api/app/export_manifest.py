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
    equipment = job.stages.get("equipment")
    equipment_result = equipment.result if equipment else {}
    return {
        "unit_id": job.job_id,
        "source_references": {view: slot.model_dump(mode="json") for view, slot in job.references.items()},
        "geometry_provider": job.actual_provider or job.requested_provider,
        "geometry_settings": geometry.result.get("settings", {}) if geometry else {},
        "texture_settings": textures.result.get("settings", {}) if textures else {},
        "retopology_settings": job.stages.get("retopology").result if job.stages.get("retopology") else {},
        "vertices": validation.get("vertex_count", 0),
        "faces": validation.get("face_count", 0),
        "materials": validation.get("material_count", 0),
        "textures": textures.result.get("images", []) if textures else [],
        "bones": validation.get("joint_count", 0),
        "canonical_mapping": rig.result.get("validation", {}).get("canonical_mapping", {}) if rig else {},
        "animations": job.export_actions,
        "motion_sources": [],
        "equipment": equipment_result.get("assets", []),
        "sockets": equipment_result.get("sockets", []),
        "ik_settings": {},
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
