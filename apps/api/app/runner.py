from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, Callable

from .job_store import JobStore
from .config import REPO_ROOT
from .model_registry import ModelRegistry
from .process_manager import ProcessManager, WorkerFailure
from .reference_pipeline import assess_reference, preprocess_reference
from .schemas import JobManifest, StageName, StageStatus


class SingleGpuQueue:
    """Process-wide serialization boundary for GPU work."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def run(self, operation: Callable[[], Awaitable[None]]) -> None:
        async with self._lock:
            await operation()


class PipelineRunner:
    def __init__(self, store: JobStore, queue: SingleGpuQueue) -> None:
        self.store = store
        self.queue = queue
        self.tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self.models = ModelRegistry()
        self.process_manager = ProcessManager()

    def _logger(self, manifest: JobManifest, stage: str) -> tuple[logging.Logger, Path]:
        log_path = self.store.job_dir(manifest.job_id) / "logs" / f"{stage}.log"
        logger = logging.getLogger(f"character_factory.{manifest.job_id}.{stage}")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger, log_path

    async def run(self, job_id: str, stage: StageName) -> None:
        key = (job_id, stage.value)
        if key in self.tasks and not self.tasks[key].done():
            raise RuntimeError("stage is already running")
        task = asyncio.create_task(self._run(job_id, stage))
        self.tasks[key] = task
        await task

    async def _run(self, job_id: str, stage: StageName) -> None:
        manifest = self.store.get(job_id)
        record = manifest.stages[stage.value]
        logger, log_path = self._logger(manifest, stage.value)
        record.status = StageStatus.RUNNING
        record.started_at = datetime.now(UTC)
        record.log_path = str(log_path.relative_to(self.store.root.parent))
        manifest.status = "RUNNING"
        self.store.save(manifest)
        started = record.started_at
        try:
            logger.info("Stage started: %s", stage.value)
            if stage is StageName.REFERENCES:
                await self._references(manifest, logger)
            elif stage is StageName.GEOMETRY:
                await self._geometry(manifest, logger, log_path)
            else:
                raise RuntimeError(f"Stage '{stage.value}' is not available until its required local provider is installed")
            record.status = StageStatus.READY
            record.result = {**record.result, "completed": True}
            logger.info("Stage completed")
        except asyncio.CancelledError:
            record.status = StageStatus.CANCELLED
            logger.warning("Stage cancelled")
            raise
        except WorkerFailure as exc:
            record.status = StageStatus.FAILED_OOM if exc.category == "FAILED_OOM" else StageStatus.FAILED
            record.error_category = exc.category
            record.error_message = str(exc)
            logger.error("Worker failed [%s]: %s", exc.category, exc)
        except Exception as exc:
            record.status = StageStatus.FAILED
            record.error_category = "STAGE_ERROR"
            record.error_message = str(exc)
            logger.exception("Stage failed")
        finally:
            record.finished_at = datetime.now(UTC)
            record.duration_seconds = (record.finished_at - started).total_seconds() if started else None
            manifest.status = "READY" if all(item.status in {StageStatus.READY, StageStatus.PENDING} for item in manifest.stages.values()) else "FAILED"
            self.store.save(manifest)
            for handler in logger.handlers:
                handler.close()
                logger.removeHandler(handler)

    async def _references(self, manifest: JobManifest, logger: logging.Logger) -> None:
        job_dir = self.store.job_dir(manifest.job_id)
        for view, slot in manifest.references.items():
            if not slot.original_path:
                continue
            source = job_dir / slot.original_path
            destination = job_dir / "references" / "processed" / f"{view}.png"
            logger.info("Processing %s", view)
            result = await asyncio.to_thread(preprocess_reference, source, destination, manifest.resolution)
            quality = assess_reference(destination)
            slot.processed_path = str(destination.relative_to(job_dir))
            slot.quality = {**result, **quality}
            if quality["level"] == "ERROR":
                raise ValueError(f"Invalid {view} reference: {'; '.join(quality['errors'])}")
            logger.info("Saved processed reference: %s", destination)

    async def _geometry(self, manifest: JobManifest, logger: logging.Logger, log_path: Path) -> None:
        reference_stage = manifest.stages[StageName.REFERENCES.value]
        if reference_stage.status is not StageStatus.READY:
            raise RuntimeError("References must be processed successfully before geometry")
        front = manifest.references.get("front")
        if not front or not front.processed_path:
            raise RuntimeError("FRONT reference is required for geometry")
        spar3d = next(item for item in self.models.status() if item["id"] == "spar3d")
        if not spar3d["installed"]:
            raise WorkerFailure("MODEL_MISSING", str(spar3d["reason"]))
        job_dir = self.store.job_dir(manifest.job_id)
        output_dir = job_dir / "geometry" / "spar3d"
        settings = {"texture_resolution": 1024, "low_vram_mode": manifest.profile == "SAFE", "remesh": "none"}
        request = {"image": str(job_dir / front.processed_path), "output_dir": str(output_dir), "settings": settings}
        logger.info("Starting official SPAR3D worker")
        result = await asyncio.to_thread(self.process_manager.run_json_worker, [sys.executable, "-m", "workers.spar3d.worker"], request, REPO_ROOT, {"SPAR3D_ROOT": str(spar3d["root"]), **({"SPAR3D_PYTHON": spar3d["python"]} if spar3d["python"] else {})}, log_path)
        mesh_path = Path(result.payload["mesh_path"])
        manifest.actual_provider = result.payload["provider"]
        manifest.stages[StageName.GEOMETRY.value].result = {"mesh_path": str(mesh_path.relative_to(job_dir)), "settings": settings, "stdout": result.stdout[-4000:]}
        logger.info("Generated mesh saved: %s", mesh_path)
