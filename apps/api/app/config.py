from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
JOBS_ROOT = REPO_ROOT / "jobs"
ASSETS_ROOT = REPO_ROOT / "assets"
EQUIPMENT_ROOT = ASSETS_ROOT / "equipment"
DATA_ROOT = REPO_ROOT / "data"
HARDWARE_PROFILE = REPO_ROOT / "hardware_profile.json"


def ensure_directories() -> None:
    for path in (JOBS_ROOT, ASSETS_ROOT, EQUIPMENT_ROOT, DATA_ROOT, REPO_ROOT / "logs"):
        path.mkdir(parents=True, exist_ok=True)


def api_host() -> str:
    return os.getenv("CHARACTER_FACTORY_HOST", "127.0.0.1")


def api_port() -> int:
    return int(os.getenv("CHARACTER_FACTORY_PORT", "8000"))
