from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .config import ensure_directories
from .animation_graph import AnimationGraph, AnimationInput, MotionClip
from .capabilities import capabilities
from .cache import clean as clean_cache, inventory as cache_inventory
from .equipment_library import EquipmentLibrary, EquipmentLibraryError
from .hardware import detect_hardware
from .job_store import JobStore
from .model_registry import ModelRegistry
from .motion_library import MotionLibrary, MotionLibraryError
from .pipeline_graph import STAGE_DEPENDENCIES
from .runner import PipelineRunner, SingleGpuQueue
from .schemas import AnimationGraphRequest, CacheCleanRequest, CacheCleanResult, CacheInventory, ClothingSelectionRequest, EquipmentRegisterRequest, EquipmentSelectionRequest, ExportSelectionRequest, JobCreateRequest, JobManifest, MotionRegisterRequest, MotionSelectionRequest, ReferenceSlot, Settings, StageName
from .storage import atomic_write_json, read_json
from .schemas import StageStatus

ensure_directories()
store = JobStore()
store.recover_incomplete()
runner = PipelineRunner(store, SingleGpuQueue())

app = FastAPI(title="Character Factory API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5176",
        "http://localhost:5176",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "character-factory-api"}


@app.get("/api/hardware")
def hardware() -> dict:
    return detect_hardware()


@app.get("/api/capabilities")
def get_capabilities() -> dict:
    return capabilities()


@app.get("/api/models")
def get_models() -> list[dict]:
    return ModelRegistry().status()


@app.get("/api/motions")
def get_motions() -> dict:
    library = MotionLibrary()
    catalog = library.catalog()
    return {**catalog, "available_clips": list(library.clips().values())}


@app.get("/api/equipment")
def get_equipment() -> dict:
    return EquipmentLibrary().catalog()


@app.post("/api/equipment/register")
def register_equipment(request: EquipmentRegisterRequest) -> dict:
    try:
        return EquipmentLibrary().register_local(Path(request.source_path), request.asset_id, request.name, request.asset_type, request.slot, request.handedness, request.primary_socket, request.secondary_grip, request.tags)
    except (EquipmentLibraryError, OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/jobs/{job_id}/equipment-selection", response_model=JobManifest)
def set_equipment_selection(job_id: str, request: EquipmentSelectionRequest) -> JobManifest:
    manifest = get_job(job_id)
    try:
        EquipmentLibrary().selected_assets(request.assets)
    except EquipmentLibraryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    manifest.equipment_assets = request.assets
    store.invalidate_from(manifest, StageName.EQUIPMENT)
    if manifest.stages[StageName.EQUIPMENT.value].status is StageStatus.READY:
        manifest.stages[StageName.EQUIPMENT.value].status = StageStatus.INVALIDATED
    manifest.stages[StageName.EQUIPMENT.value].result = {}
    manifest.stages[StageName.EQUIPMENT.value].error_category = "UPSTREAM_CHANGED"
    manifest.stages[StageName.EQUIPMENT.value].error_message = "Equipment selection changed; attach the selected assets"
    store.save(manifest)
    return manifest


@app.put("/api/jobs/{job_id}/clothing-selection", response_model=JobManifest)
def set_clothing_selection(job_id: str, request: ClothingSelectionRequest) -> JobManifest:
    manifest = get_job(job_id)
    try:
        selected = EquipmentLibrary().selected_assets(request.assets)
    except EquipmentLibraryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    invalid = [str(asset["id"]) for asset in selected if asset.get("asset_type") not in {"CLOTHING_SKINNED", "ARMOR_SKINNED", "ACCESSORY_SKINNED"}]
    if invalid:
        raise HTTPException(status_code=400, detail="Only skinned clothing/armor/accessories may be selected: " + ", ".join(invalid))
    manifest.clothing_assets = request.assets
    store.invalidate_from(manifest, StageName.CLOTHING)
    manifest.stages[StageName.CLOTHING.value].status = StageStatus.INVALIDATED
    manifest.stages[StageName.CLOTHING.value].result = {}
    manifest.stages[StageName.CLOTHING.value].error_category = "UPSTREAM_CHANGED"
    manifest.stages[StageName.CLOTHING.value].error_message = "Clothing selection changed; transfer weights onto the character rig"
    store.save(manifest)
    return manifest


@app.post("/api/motions/register")
def register_motion_library(request: MotionRegisterRequest) -> dict:
    try:
        return MotionLibrary().register_local(Path(request.source_path), request.library_id, request.source_id, request.license, request.allowed_for_commercial_use)
    except (MotionLibraryError, OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.put("/api/jobs/{job_id}/export-selection", response_model=JobManifest)
def set_export_selection(job_id: str, request: ExportSelectionRequest) -> JobManifest:
    manifest = get_job(job_id)
    manifest.export_actions = request.actions
    if manifest.stages[StageName.EXPORT.value].status is StageStatus.READY:
        manifest.stages[StageName.EXPORT.value].status = StageStatus.INVALIDATED
        manifest.stages[StageName.EXPORT.value].error_category = "UPSTREAM_CHANGED"
        manifest.stages[StageName.EXPORT.value].error_message = "Export selection changed; export the selected actions"
    manifest.stages[StageName.EXPORT.value].result = {}
    store.save(manifest)
    return manifest


@app.put("/api/jobs/{job_id}/motion-selection", response_model=JobManifest)
def set_motion_selection(job_id: str, request: MotionSelectionRequest) -> JobManifest:
    manifest = get_job(job_id)
    try:
        MotionLibrary().selected_clips(request.clips)
    except MotionLibraryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    manifest.motion_clips = request.clips
    store.invalidate_from(manifest, StageName.MOTIONS)
    if manifest.stages[StageName.MOTIONS.value].status is StageStatus.READY:
        manifest.stages[StageName.MOTIONS.value].status = StageStatus.INVALIDATED
    manifest.stages[StageName.MOTIONS.value].result = {}
    manifest.stages[StageName.MOTIONS.value].error_category = "UPSTREAM_CHANGED"
    manifest.stages[StageName.MOTIONS.value].error_message = "Motion selection changed; normalize the selected clips"
    store.save(manifest)
    return manifest


@app.post("/api/jobs/{job_id}/animation-graph")
def evaluate_animation_graph(job_id: str, request: AnimationGraphRequest) -> dict:
    manifest = get_job(job_id)
    motions = manifest.stages[StageName.MOTIONS.value]
    if motions.status.value != "READY":
        raise HTTPException(status_code=409, detail="Animation graph requires READY normalized motions")
    clips: list[MotionClip] = []
    for item in motions.result.get("clips", []):
        worker = item.get("worker", {})
        clips.append(MotionClip(id=str(item["clip_id"]), name=str(worker.get("normalized_action") or item["action"]), category=str(item.get("category") or item["action"]), duration=float(item.get("duration") or 1.0), loop=bool(item.get("loop", False)), required_equipment_type=item.get("required_equipment_type"), direction_degrees=item.get("direction_degrees"), layer=str(item.get("layer") or "base"), additive=bool(item.get("additive", False)), root_motion=bool(item.get("root_motion", True)), speed=item.get("speed")))
    if not clips:
        raise HTTPException(status_code=409, detail="Normalized motions contain no clips")
    output = AnimationGraph(clips).evaluate(AnimationInput(**request.model_dump()))
    return asdict(output)


@app.get("/api/settings", response_model=Settings)
def get_settings() -> Settings:
    raw = read_json(Path(__file__).resolve().parents[3] / "data" / "settings.json", {})
    return Settings.model_validate(raw)


@app.put("/api/settings", response_model=Settings)
def put_settings(settings: Settings) -> Settings:
    path = Path(__file__).resolve().parents[3] / "data" / "settings.json"
    atomic_write_json(path, settings.model_dump(mode="json"))
    return settings


@app.get("/api/cache", response_model=CacheInventory)
def get_cache() -> CacheInventory:
    return CacheInventory(items=cache_inventory(store))


@app.post("/api/cache/clean", response_model=CacheCleanResult)
def post_cache_clean(request: CacheCleanRequest) -> CacheCleanResult:
    try:
        return CacheCleanResult.model_validate(clean_cache(store, request.job_ids))
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/jobs", response_model=list[JobManifest])
def list_jobs() -> list[JobManifest]:
    return store.list()


@app.post("/api/jobs", response_model=JobManifest, status_code=201)
def create_job(request: JobCreateRequest) -> JobManifest:
    return store.create(request)


@app.get("/api/jobs/{job_id}", response_model=JobManifest)
def get_job(job_id: str) -> JobManifest:
    try:
        return store.get(job_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Job not found")


@app.post("/api/jobs/{job_id}/references/{view}", response_model=JobManifest)
async def upload_reference(job_id: str, view: str, file: UploadFile = File(...)) -> JobManifest:
    view = view.lower()
    if view not in {"front", "left", "back", "right"}:
        raise HTTPException(status_code=400, detail="view must be front, left, back, or right")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are supported")
    get_job(job_id)
    suffix = Path(file.filename or "reference.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=415, detail="Supported image formats: PNG, JPG, WEBP")
    relative = Path("references") / "original" / f"{view}{suffix}"
    destination = store.job_dir(job_id) / relative
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Reference image is larger than 25 MB")
    # Re-read after receiving the upload: a worker may have started while the
    # request was streaming. Never replace inputs used by an active stage.
    manifest = get_job(job_id)
    if any(record.status.value == "RUNNING" for record in manifest.stages.values()) or any(
        key[0] == job_id and not task.done() for key, task in runner.tasks.items()
    ):
        raise HTTPException(status_code=409, detail="Cancel the running stage before replacing a reference")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    manifest.references[view] = ReferenceSlot(view=view, required=view == "front", original_path=str(relative))
    store.invalidate_from(manifest, StageName.REFERENCES)
    reference_stage = manifest.stages[StageName.REFERENCES.value]
    reference_stage.status = StageStatus.INVALIDATED
    reference_stage.error_category = "UPSTREAM_CHANGED"
    reference_stage.error_message = f"The {view} reference changed; process references again"
    reference_stage.result = {}
    manifest.status = "INVALIDATED"
    store.save(manifest)
    return manifest


@app.post("/api/jobs/{job_id}/stages/{stage}/run")
async def run_stage(job_id: str, stage: str) -> dict[str, str]:
    try:
        stage_name = StageName(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown stage: {stage}")
    get_job(job_id)
    try:
        manifest = store.get(job_id)
        for dependency in STAGE_DEPENDENCIES[stage_name]:
            if manifest.stages[dependency.value].status.value != "READY":
                raise HTTPException(status_code=409, detail=f"Stage '{stage}' requires READY dependency '{dependency.value}'")
    except HTTPException:
        raise
    asyncio.create_task(runner.run(job_id, stage_name))
    return {"status": "QUEUED", "stage": stage_name.value}


@app.post("/api/jobs/{job_id}/stages/{stage}/cancel")
async def cancel_stage(job_id: str, stage: str) -> dict[str, bool]:
    try:
        stage_name = StageName(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown stage: {stage}")
    get_job(job_id)
    return {"cancelled": await runner.cancel(job_id, stage_name)}


@app.get("/api/jobs/{job_id}/files/{path:path}")
def job_file(job_id: str, path: str):
    job_dir = store.job_dir(job_id)
    requested = (job_dir / path).resolve()
    if job_dir.resolve() not in requested.parents:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(requested)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    get_job(job_id)

    async def events():
        last = ""
        for _ in range(600):
            manifest = store.get(job_id)
            encoded = json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False)
            if encoded != last:
                yield f"data: {encoded}\n\n"
                last = encoded
            if manifest.status in {"READY", "FAILED", "CANCELLED"}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")
