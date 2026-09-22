from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    FAILED = "FAILED"
    FAILED_OOM = "FAILED_OOM"
    INVALIDATED = "INVALIDATED"
    CANCELLED = "CANCELLED"


class StageName(str, Enum):
    REFERENCES = "references"
    GEOMETRY = "geometry"
    TEXTURES = "textures"
    RETOPOLOGY = "retopology"
    RIG = "rig"
    CLOTHING = "clothing"
    EQUIPMENT = "equipment"
    IK = "ik"
    MOTIONS = "motions"
    EXPORT = "export"


class StageRecord(BaseModel):
    name: StageName
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    error_category: str | None = None
    error_message: str | None = None
    log_path: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


QualityProfile = Literal["SAFE", "BALANCED", "MAX", "CUSTOM"]
ProviderName = Literal["AUTO", "Spar3DProvider", "HunyuanMultiviewProvider", "HunyuanSingleViewProvider"]


class ReferenceSlot(BaseModel):
    view: str
    required: bool = False
    original_path: str | None = None
    processed_path: str | None = None
    quality: dict[str, Any] | None = None


class JobManifest(BaseModel):
    job_id: str
    created_at: datetime
    updated_at: datetime
    status: str = "CREATED"
    profile: QualityProfile = "BALANCED"
    resolution: int = Field(default=768, ge=384, le=1536)
    requested_provider: ProviderName = "AUTO"
    actual_provider: str | None = None
    fallback_reason: str | None = None
    references: dict[str, ReferenceSlot] = Field(default_factory=dict)
    stages: dict[str, StageRecord] = Field(default_factory=dict)
    pipeline_version: str = "0.1.0"
    equipment_assets: list[str] = Field(default_factory=list)
    clothing_assets: list[str] = Field(default_factory=list)
    motion_clips: list[str] = Field(default_factory=list)
    export_actions: list[str] = Field(default_factory=list)
    retopology_mode: Literal["KEEP_SOURCE", "TRIANGLE", "QUAD"] = "TRIANGLE"
    retopology_target_faces: int = Field(default=30000, ge=5000, le=80000)
    inference_steps: int = Field(default=50, ge=20, le=100)
    octree_resolution: int = Field(default=384, ge=256, le=512)
    geometry_num_chunks: int = Field(default=20000, ge=5000, le=50000)
    low_vram_mode: bool = True
    texture_resolution: Literal[512, 1024, 2048] = 1024
    warnings: list[str] = Field(default_factory=list)


class JobCreateRequest(BaseModel):
    name: str = "Character Unit"
    profile: QualityProfile = "BALANCED"
    resolution: int = Field(default=768, ge=384, le=1536)
    requested_provider: ProviderName = "AUTO"


class JobSettingsRequest(BaseModel):
    profile: QualityProfile = "BALANCED"
    resolution: int = Field(default=768, ge=384, le=1536)
    requested_provider: ProviderName = "AUTO"
    inference_steps: int = Field(default=50, ge=20, le=100)
    octree_resolution: int = Field(default=384, ge=256, le=512)
    geometry_num_chunks: int = Field(default=20000, ge=5000, le=50000)
    low_vram_mode: bool = True
    texture_resolution: Literal[512, 1024, 2048] = 1024


class Settings(BaseModel):
    profile: str = "BALANCED"
    vram_budget_gb: float = 10.0
    reserve_vram_gb: float = 1.5
    preferred_resolution: int = Field(default=768, ge=384, le=1536)
    api_host: str = "127.0.0.1"
    allow_external_api: bool = False


class MotionRegisterRequest(BaseModel):
    source_path: str
    library_id: str
    source_id: str
    license: str
    allowed_for_commercial_use: bool = False


class ExportSelectionRequest(BaseModel):
    actions: list[str] = Field(default_factory=list)


class MotionSelectionRequest(BaseModel):
    clips: list[str] = Field(default_factory=list)


class EquipmentSelectionRequest(BaseModel):
    assets: list[str] = Field(default_factory=list)


class ClothingSelectionRequest(BaseModel):
    assets: list[str] = Field(default_factory=list)


class RetopologySettingsRequest(BaseModel):
    mode: Literal["KEEP_SOURCE", "TRIANGLE", "QUAD"] = "TRIANGLE"
    target_faces: int = Field(default=30000, ge=5000, le=80000)


class EquipmentRegisterRequest(BaseModel):
    source_path: str
    asset_id: str
    name: str
    asset_type: str
    slot: str
    handedness: str | None = None
    primary_socket: str | None = None
    secondary_grip: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class AnimationGraphRequest(BaseModel):
    speed: float = 0.0
    direction_degrees: float = 0.0
    grounded: bool = True
    crouched: bool = False
    sprinting: bool = False
    equipment_type: str | None = None
    action: str | None = None
    action_time: float = 0.0
    combo_index: int = 0
    previous_state: str | None = None
    delta_time: float = 0.0
    root_motion_enabled: bool = True
    upper_body_action: str | None = None
    emote: str | None = None
    vertical_velocity: float = 0.0
    transition_duration: float | None = None


class CacheCleanRequest(BaseModel):
    job_ids: list[str] = Field(default_factory=list, min_length=1)


class CacheItem(BaseModel):
    job_id: str
    status: str
    cache_bytes: int
    protected_bytes: int
    cleanable: bool
    reason: str


class CacheInventory(BaseModel):
    items: list[CacheItem] = Field(default_factory=list)


class CacheCleanResult(BaseModel):
    cleaned: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, str]] = Field(default_factory=list)
    deleted_bytes: int = 0
