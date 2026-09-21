from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, Callable

from .job_store import JobStore
from .config import REPO_ROOT
from .model_registry import ModelRegistry
from .motion_library import MotionLibrary
from .equipment_library import EquipmentLibrary
from .pipeline_graph import STAGE_DEPENDENCIES
from .process_manager import ProcessManager, WorkerFailure
from tools.validation.glb import extract_glb_images, validate_glb
from .export_manifest import save_unit_manifest
from .vram_monitor import VramMonitor
from .reference_pipeline import assess_reference, preprocess_reference
from .schemas import JobManifest, StageName, StageStatus
from tools.validation.rig import validate_rigged_glb


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
        manifest = self.store.get(job_id)
        for dependency in STAGE_DEPENDENCIES[stage]:
            if manifest.stages[dependency.value].status is not StageStatus.READY:
                raise RuntimeError(f"Stage '{stage.value}' requires READY dependency '{dependency.value}'")
        self.store.invalidate_from(manifest, stage)
        self.store.save(manifest)
        task = asyncio.create_task(self._run(job_id, stage))
        self.tasks[key] = task
        await task

    async def cancel(self, job_id: str, stage: StageName) -> bool:
        task = self.tasks.get((job_id, stage.value))
        if not task or task.done():
            return False
        task.cancel()
        return True

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
            heavy_stages = {StageName.GEOMETRY, StageName.RETOPOLOGY, StageName.RIG, StageName.EQUIPMENT, StageName.MOTIONS, StageName.EXPORT}
            if stage in heavy_stages:
                await self.queue.run(lambda: self._execute_stage(manifest, stage, logger, log_path))
            else:
                await self._execute_stage(manifest, stage, logger, log_path)
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

    async def _execute_stage(self, manifest: JobManifest, stage: StageName, logger: logging.Logger, log_path: Path) -> None:
        if stage is StageName.REFERENCES:
            await self._references(manifest, logger)
        elif stage is StageName.GEOMETRY:
            await self._geometry(manifest, logger, log_path)
        elif stage is StageName.TEXTURES:
            await self._textures(manifest, logger)
        elif stage is StageName.RETOPOLOGY:
            await self._retopology(manifest, logger, log_path)
        elif stage is StageName.RIG:
            await self._rig(manifest, logger, log_path)
        elif stage is StageName.EQUIPMENT:
            await self._equipment(manifest, logger, log_path)
        elif stage is StageName.MOTIONS:
            await self._motions(manifest, logger, log_path)
        elif stage is StageName.EXPORT:
            await self._export(manifest, logger, log_path)
        else:
            raise RuntimeError(f"Stage '{stage.value}' is not available until its required local provider is installed")

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
        retry_history: list[dict] = []
        result = None
        vram_metrics: dict = {}
        for attempt in range(3):
            attempt_log = log_path.with_name(f"geometry_attempt_{attempt + 1}.log")
            request = {"image": str(job_dir / front.processed_path), "output_dir": str(output_dir / f"attempt_{attempt + 1}"), "settings": settings}
            logger.info("Starting official SPAR3D worker, attempt %s, settings=%s", attempt + 1, settings)
            monitor = VramMonitor()
            before = monitor.snapshot()
            monitor.start()
            try:
                result = await asyncio.to_thread(self.process_manager.run_json_worker, [sys.executable, "-m", "workers.spar3d.worker"], request, REPO_ROOT, {"SPAR3D_ROOT": str(spar3d["root"]), **({"SPAR3D_PYTHON": spar3d["python"]} if spar3d["python"] else {})}, attempt_log)
            except WorkerFailure as error:
                metrics = monitor.stop()
                metrics["before"] = before or metrics.get("before")
                retry_history.append({"attempt": attempt + 1, "settings": settings.copy(), "category": error.category, "message": str(error), "vram": metrics})
                if error.category != "FAILED_OOM" or attempt >= 2:
                    raise WorkerFailure(error.category, f"{error}; retry_history={retry_history}") from error
                settings = {**settings, "low_vram_mode": True, "texture_resolution": max(384, int(settings["texture_resolution"]) // 2)}
                logger.warning("CUDA OOM; retrying with downgraded settings=%s", settings)
                continue
            else:
                vram_metrics = monitor.stop()
                vram_metrics["before"] = before or vram_metrics.get("before")
                break
        if result is None:
            raise WorkerFailure("WORKER_ERROR", "Geometry worker completed without a result")
        mesh_path = Path(result.payload["mesh_path"])
        report = validate_glb(mesh_path)
        if not report.valid:
            raise WorkerFailure("PROVIDER_OUTPUT_INVALID", "; ".join(report.errors))
        manifest.actual_provider = result.payload["provider"]
        manifest.stages[StageName.GEOMETRY.value].result = {"mesh_path": str(mesh_path.relative_to(job_dir)), "settings": settings, "retry_history": retry_history, "vram": vram_metrics, "stdout": result.stdout[-4000:], "validation": report.__dict__}
        logger.info("Generated mesh saved: %s", mesh_path)

    async def _textures(self, manifest: JobManifest, logger: logging.Logger) -> None:
        geometry = manifest.stages[StageName.GEOMETRY.value]
        mesh_value = geometry.result.get("mesh_path")
        if not geometry.status is StageStatus.READY or not isinstance(mesh_value, str):
            raise RuntimeError("Geometry must be READY before texture extraction")
        job_dir = self.store.job_dir(manifest.job_id)
        mesh_path = job_dir / mesh_value
        report = validate_glb(mesh_path)
        if not report.valid:
            raise WorkerFailure("GEOMETRY_INVALID", "; ".join(report.errors))
        texture_dir = job_dir / "textures" / "source"
        images = await asyncio.to_thread(extract_glb_images, mesh_path, texture_dir)
        materials = report.material_count
        warnings: list[str] = []
        if materials and not images:
            warnings.append("GLB contains materials but no embedded image textures; only material factors are available")
        if not materials and not images:
            warnings.append("Provider output has no material or texture data")
        manifest.stages[StageName.TEXTURES.value].result = {"source_mesh": mesh_value, "images": [{**item, "path": str(Path(item["path"]).relative_to(job_dir))} for item in images], "material_count": materials, "warnings": warnings}
        manifest.warnings.extend(warnings)
        logger.info("Extracted %s embedded texture images", len(images))

    async def _retopology(self, manifest: JobManifest, logger: logging.Logger, log_path: Path) -> None:
        textures = manifest.stages[StageName.TEXTURES.value]
        mesh_value = textures.result.get("source_mesh")
        if textures.status is not StageStatus.READY or not isinstance(mesh_value, str):
            raise RuntimeError("Textures must be READY before retopology")
        blender = shutil.which("blender")
        if not blender:
            raise WorkerFailure("BLENDER_MISSING", "Blender executable was not found")
        job_dir = self.store.job_dir(manifest.job_id)
        source_mesh = job_dir / mesh_value
        output_mesh = job_dir / "retopology" / "triangle.glb"
        request = {"source_mesh": str(source_mesh), "output_mesh": str(output_mesh), "mode": "TRIANGLE", "target_faces": 30000}
        logger.info("Starting Blender retopology worker: %s", request)
        result = await asyncio.to_thread(self.process_manager.run_json_worker, [sys.executable, "-m", "workers.blender.worker"], request, REPO_ROOT, {"BLENDER_PATH": blender}, log_path)
        report = validate_glb(output_mesh)
        if not report.valid:
            raise WorkerFailure("RETOPOLOGY_OUTPUT_INVALID", "; ".join(report.errors))
        manifest.stages[StageName.RETOPOLOGY.value].result = {"mode": result.payload.get("mode"), "source_mesh": mesh_value, "mesh_path": str(output_mesh.relative_to(job_dir)), "target_faces": request["target_faces"], "validation": report.__dict__}
        logger.info("Retopology output saved: %s", output_mesh)

    async def _rig(self, manifest: JobManifest, logger: logging.Logger, log_path: Path) -> None:
        retopo = manifest.stages[StageName.RETOPOLOGY.value]
        mesh_value = retopo.result.get("mesh_path")
        if retopo.status is not StageStatus.READY or not isinstance(mesh_value, str):
            raise RuntimeError("Retopology must be READY before rigging")
        job_dir = self.store.job_dir(manifest.job_id)
        source_mesh = job_dir / mesh_value
        output_dir = job_dir / "rig"
        request = {"source_mesh": str(source_mesh), "output_dir": str(output_dir)}
        unirig_root = os.getenv("UNIRIG_ROOT")
        env = {"UNIRIG_ROOT": unirig_root} if unirig_root else {}
        logger.info("Starting official UniRig worker")
        result = await asyncio.to_thread(self.process_manager.run_json_worker, [sys.executable, "-m", "workers.unirig.worker"], request, REPO_ROOT, env, log_path)
        rigged_mesh = Path(result.payload["rigged_mesh"])
        report = validate_rigged_glb(rigged_mesh, require_canonical=False)
        if not report.valid:
            raise WorkerFailure("RIG_VALIDATION_FAILED", "; ".join(report.errors))
        manifest.stages[StageName.RIG.value].result = {"provider": result.payload["provider"], "source_mesh": mesh_value, "mesh_path": str(rigged_mesh.relative_to(job_dir)), "skeleton": str(Path(result.payload["skeleton"]).relative_to(job_dir)), "skin": str(Path(result.payload["skin"]).relative_to(job_dir)), "validation": report.__dict__}
        logger.info("Rigged GLB saved: %s", rigged_mesh)

    async def _export(self, manifest: JobManifest, logger: logging.Logger, log_path: Path) -> None:
        if not manifest.export_actions:
            raise RuntimeError("Select at least one normalized action before export")
        rig = manifest.stages[StageName.RIG.value]
        mesh_value = rig.result.get("mesh_path")
        if rig.status is not StageStatus.READY or not isinstance(mesh_value, str):
            raise RuntimeError("Rig must be READY before export")
        blender = shutil.which("blender")
        if not blender:
            raise WorkerFailure("BLENDER_MISSING", "Blender executable was not found")
        job_dir = self.store.job_dir(manifest.job_id)
        equipment = manifest.stages[StageName.EQUIPMENT.value]
        equipment_mesh = equipment.result.get("mesh_path") if equipment.status is StageStatus.READY else None
        source_mesh = job_dir / (equipment_mesh if isinstance(equipment_mesh, str) else mesh_value)
        glb_path = job_dir / "export" / "unit.glb"
        fbx_path = job_dir / "export" / "unit.fbx"
        request = {"source_mesh": str(source_mesh), "glb_output": str(glb_path), "fbx_output": str(fbx_path), "selected_actions": manifest.export_actions}
        logger.info("Starting Blender export worker: %s", request)
        result = await asyncio.to_thread(self.process_manager.run_json_worker, [sys.executable, "-m", "workers.blender.export_worker"], request, REPO_ROOT, {"BLENDER_PATH": blender}, log_path)
        roundtrip = result.payload.get("roundtrip", {})
        glb_report = validate_glb(glb_path, require_skeleton=True, require_animations=True)
        rig_report = validate_rigged_glb(glb_path, require_canonical=False)
        if not glb_report.valid or not rig_report.valid:
            raise WorkerFailure("EXPORT_ROUNDTRIP_FAILED", "; ".join(glb_report.errors + rig_report.errors))
        manifest_path = save_unit_manifest(manifest, job_dir, glb_path, fbx_path, {**roundtrip, "glb": glb_report.__dict__, "rig": rig_report.__dict__})
        manifest.stages[StageName.EXPORT.value].result = {"glb_path": str(glb_path.relative_to(job_dir)), "fbx_path": str(fbx_path.relative_to(job_dir)), "manifest_path": str(manifest_path.relative_to(job_dir)), "selected_actions": manifest.export_actions, "roundtrip": {**roundtrip, "glb": glb_report.__dict__, "rig": rig_report.__dict__}}
        logger.info("Export completed: %s", glb_path)

    async def _equipment(self, manifest: JobManifest, logger: logging.Logger, log_path: Path) -> None:
        if not manifest.equipment_assets:
            raise RuntimeError("Select at least one equipment asset before attachment")
        rig = manifest.stages[StageName.RIG.value]
        mesh_value = rig.result.get("mesh_path")
        if rig.status is not StageStatus.READY or not isinstance(mesh_value, str):
            raise RuntimeError("Rig must be READY before equipment attachment")
        blender = shutil.which("blender")
        if not blender:
            raise WorkerFailure("BLENDER_MISSING", "Blender executable was not found")
        job_dir = self.store.job_dir(manifest.job_id)
        assets = EquipmentLibrary().selected_assets(manifest.equipment_assets)
        for asset in assets:
            asset_path = Path(str(asset["asset_path"]))
            if not asset_path.is_file():
                raise WorkerFailure("EQUIPMENT_SOURCE_MISSING", f"Equipment source does not exist: {asset_path}")
        output_mesh = job_dir / "equipment" / "attached.glb"
        request = {"target_rig": str(job_dir / mesh_value), "output_mesh": str(output_mesh), "assets": assets}
        logger.info("Attaching %s equipment assets", len(assets))
        result = await asyncio.to_thread(self.process_manager.run_json_worker, [sys.executable, "-m", "workers.blender.equipment_worker"], request, REPO_ROOT, {"BLENDER_PATH": blender}, log_path)
        report = validate_glb(output_mesh, require_skeleton=True)
        rig_report = validate_rigged_glb(output_mesh, require_canonical=False)
        if not report.valid or not rig_report.valid:
            raise WorkerFailure("EQUIPMENT_OUTPUT_INVALID", "; ".join(report.errors + rig_report.errors))
        manifest.stages[StageName.EQUIPMENT.value].result = {"mesh_path": str(output_mesh.relative_to(job_dir)), "assets": assets, "sockets": result.payload.get("sockets", []), "worker": result.payload, "validation": {"glb": report.__dict__, "rig": rig_report.__dict__}}
        logger.info("Equipment output saved: %s", output_mesh)

    async def _motions(self, manifest: JobManifest, logger: logging.Logger, log_path: Path) -> None:
        if not manifest.motion_clips:
            raise RuntimeError("Select at least one installed motion clip before normalization")
        rig = manifest.stages[StageName.RIG.value]
        mesh_value = rig.result.get("mesh_path")
        if rig.status is not StageStatus.READY or not isinstance(mesh_value, str):
            raise RuntimeError("Rig must be READY before motion normalization")
        blender = shutil.which("blender")
        if not blender:
            raise WorkerFailure("BLENDER_MISSING", "Blender executable was not found")
        job_dir = self.store.job_dir(manifest.job_id)
        target_rig = job_dir / mesh_value
        clips = MotionLibrary().selected_clips(manifest.motion_clips)
        normalized: list[dict] = []
        for index, clip in enumerate(clips):
            source_motion = Path(str(clip["source_file"]))
            if not source_motion.is_file():
                raise WorkerFailure("MOTION_SOURCE_MISSING", f"Motion source does not exist: {source_motion}")
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(clip["name"])).strip("._") or f"clip_{index:03d}"
            output_mesh = job_dir / "motions" / "normalized" / f"{index:03d}_{safe_name}.glb"
            request = {"source_motion": str(source_motion), "target_rig": str(target_rig), "output_mesh": str(output_mesh), "action": clip["name"]}
            logger.info("Normalizing motion clip %s", clip["id"])
            result = await asyncio.to_thread(self.process_manager.run_json_worker, [sys.executable, "-m", "workers.blender.normalize_worker"], request, REPO_ROOT, {"BLENDER_PATH": blender}, log_path)
            report = validate_glb(output_mesh, require_skeleton=True, require_animations=True)
            rig_report = validate_rigged_glb(output_mesh, require_canonical=False)
            if not report.valid or not rig_report.valid:
                raise WorkerFailure("MOTION_OUTPUT_INVALID", "; ".join(report.errors + rig_report.errors))
            normalized.append({"clip_id": clip["id"], "source": clip["source_file"], "action": clip["name"], "category": clip.get("category", clip["name"]), "duration": clip.get("duration"), "loop": clip.get("loop", False), "required_equipment_type": clip.get("requiredEquipmentType"), "mesh_path": str(output_mesh.relative_to(job_dir)), "license": clip["license"], "allowed_for_commercial_use": clip["allowed_for_commercial_use"], "worker": result.payload, "validation": {"glb": report.__dict__, "rig": rig_report.__dict__}})
        manifest.stages[StageName.MOTIONS.value].result = {"clips": normalized, "target_rig": mesh_value}
        logger.info("Normalized %s motion clips", len(normalized))
