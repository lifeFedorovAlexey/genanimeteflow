from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from .config import JOBS_ROOT
from .schemas import JobManifest, JobCreateRequest, StageName, StageRecord, StageStatus
from .pipeline_graph import downstream
from .storage import atomic_write_json, read_json


class JobStore:
    def __init__(self, root: Path = JOBS_ROOT) -> None:
        self.root = root
        self._lock = RLock()
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        path = (self.root / job_id).resolve()
        if path.parent != self.root.resolve():
            raise ValueError("Invalid job id")
        return path

    def create(self, request: JobCreateRequest) -> JobManifest:
        job_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        stages = {stage.value: StageRecord(name=stage) for stage in StageName}
        manifest = JobManifest(
            job_id=job_id,
            created_at=now,
            updated_at=now,
            profile=request.profile,
            resolution=request.resolution,
            requested_provider=request.requested_provider,
            stages=stages,
        )
        path = self.job_dir(job_id)
        for name in ("references/original", "references/processed", "geometry", "textures", "retopology", "rig", "motions", "clothing", "equipment", "export", "logs"):
            (path / name).mkdir(parents=True, exist_ok=True)
        self.save(manifest)
        return manifest

    def save(self, manifest: JobManifest) -> JobManifest:
        with self._lock:
            manifest.updated_at = datetime.now(UTC)
            atomic_write_json(self.job_dir(manifest.job_id) / "job.json", manifest.model_dump(mode="json"))
        return manifest

    def get(self, job_id: str) -> JobManifest:
        raw = read_json(self.job_dir(job_id) / "job.json")
        if raw is None:
            raise FileNotFoundError(job_id)
        return JobManifest.model_validate(raw)

    def list(self) -> list[JobManifest]:
        result: list[JobManifest] = []
        for path in self.root.iterdir():
            if path.is_dir() and (path / "job.json").exists():
                try:
                    result.append(self.get(path.name))
                except (ValueError, OSError):
                    continue
        return sorted(result, key=lambda item: item.updated_at, reverse=True)

    def recover_incomplete(self) -> int:
        recovered = 0
        for manifest in self.list():
            changed = False
            for record in manifest.stages.values():
                if record.status is StageStatus.RUNNING:
                    record.status = StageStatus.CANCELLED
                    record.error_category = "APP_RESTARTED"
                    record.error_message = "Stage was interrupted because the API process restarted"
                    changed = True
            if changed:
                manifest.status = "FAILED"
                self.save(manifest)
                recovered += 1
        return recovered

    def invalidate_from(self, manifest: JobManifest, stage: StageName) -> None:
        for dependent in downstream(stage):
            record = manifest.stages[dependent.value]
            if dependent is not stage and record.status not in {StageStatus.PENDING, StageStatus.INVALIDATED}:
                record.status = StageStatus.INVALIDATED
                record.error_category = "UPSTREAM_CHANGED"
                record.error_message = f"Invalidated because {stage.value} was rerun"
