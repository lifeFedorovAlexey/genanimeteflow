from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .job_store import JobStore
from .schemas import JobManifest, StageName, StageStatus


# Inputs and validated exports are never cache. Everything else is disposable
# only for jobs that are not currently being built or presented as READY.
CLEANABLE_DIRECTORIES = tuple(
    stage.value for stage in StageName if stage not in {StageName.REFERENCES, StageName.EXPORT}
) + ("logs",)
PROTECTED_DIRECTORIES = ("references", "export")


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _job_cache_bytes(job_dir: Path) -> int:
    return sum(_directory_size(job_dir / name) for name in CLEANABLE_DIRECTORIES)


def _protected_bytes(job_dir: Path) -> int:
    return sum(_directory_size(job_dir / name) for name in PROTECTED_DIRECTORIES) + (
        (job_dir / "job.json").stat().st_size if (job_dir / "job.json").is_file() else 0
    )


def _running(manifest: JobManifest) -> bool:
    return any(stage.status is StageStatus.RUNNING for stage in manifest.stages.values())


def _cleanable(manifest: JobManifest) -> tuple[bool, str]:
    if _running(manifest):
        return False, "A stage is running"
    if manifest.status == "READY":
        return False, "Validated export is protected"
    return True, "Intermediate outputs can be rebuilt"


def inventory(store: JobStore) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for manifest in store.list():
        job_dir = store.job_dir(manifest.job_id)
        cleanable, reason = _cleanable(manifest)
        result.append(
            {
                "job_id": manifest.job_id,
                "status": manifest.status,
                "cache_bytes": _job_cache_bytes(job_dir),
                "protected_bytes": _protected_bytes(job_dir),
                "cleanable": cleanable,
                "reason": reason,
            }
        )
    return result


def clean(store: JobStore, job_ids: list[str]) -> dict[str, Any]:
    cleaned: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for job_id in dict.fromkeys(job_ids):
        manifest = store.get(job_id)
        can_clean, reason = _cleanable(manifest)
        if not can_clean:
            skipped.append({"job_id": job_id, "reason": reason})
            continue
        job_dir = store.job_dir(job_id)
        deleted_bytes = _job_cache_bytes(job_dir)
        for directory in CLEANABLE_DIRECTORIES:
            target = job_dir / directory
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
        for stage in StageName:
            if stage in {StageName.REFERENCES, StageName.EXPORT}:
                continue
            record = manifest.stages[stage.value]
            if record.status is not StageStatus.PENDING:
                record.status = StageStatus.INVALIDATED
                record.error_category = "CACHE_CLEARED"
                record.error_message = "Intermediate output was cleared; rerun this stage"
                record.result = {}
                record.log_path = None
        manifest.status = "INVALIDATED"
        store.save(manifest)
        cleaned.append({"job_id": job_id, "deleted_bytes": deleted_bytes})
    return {"cleaned": cleaned, "skipped": skipped, "deleted_bytes": sum(item["deleted_bytes"] for item in cleaned)}
