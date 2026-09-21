from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .config import ensure_directories
from .capabilities import capabilities
from .hardware import detect_hardware
from .job_store import JobStore
from .model_registry import ModelRegistry
from .pipeline_graph import STAGE_DEPENDENCIES
from .runner import PipelineRunner, SingleGpuQueue
from .schemas import JobCreateRequest, JobManifest, ReferenceSlot, Settings, StageName
from .storage import atomic_write_json, read_json

ensure_directories()
store = JobStore()
store.recover_incomplete()
runner = PipelineRunner(store, SingleGpuQueue())

app = FastAPI(title="Character Factory API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


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


@app.get("/api/settings", response_model=Settings)
def get_settings() -> Settings:
    raw = read_json(Path(__file__).resolve().parents[3] / "data" / "settings.json", {})
    return Settings.model_validate(raw)


@app.put("/api/settings", response_model=Settings)
def put_settings(settings: Settings) -> Settings:
    path = Path(__file__).resolve().parents[3] / "data" / "settings.json"
    atomic_write_json(path, settings.model_dump(mode="json"))
    return settings


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
    manifest = get_job(job_id)
    suffix = Path(file.filename or "reference.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=415, detail="Supported image formats: PNG, JPG, WEBP")
    relative = Path("references") / "original" / f"{view}{suffix}"
    destination = store.job_dir(job_id) / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Reference image is larger than 25 MB")
    destination.write_bytes(content)
    manifest.references[view] = ReferenceSlot(view=view, required=view == "front", original_path=str(relative))
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
            if manifest.status in {"READY", "FAILED"}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")
