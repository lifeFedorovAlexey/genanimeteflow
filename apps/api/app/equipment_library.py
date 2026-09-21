from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .config import EQUIPMENT_ROOT
from .storage import atomic_write_json
from tools.validation.glb import validate_glb


class EquipmentLibraryError(RuntimeError):
    """An equipment asset or manifest failed validation."""


SKINNED_TYPES = {"CLOTHING_SKINNED", "ARMOR_SKINNED", "ACCESSORY_SKINNED"}
VALID_TYPES = {"BODY", "CLOTHING_SKINNED", "ARMOR_SKINNED", "ARMOR_RIGID", "PROP_RIGID", "ACCESSORY_SKINNED", "ACCESSORY_RIGID", "WEAPON", "TOOL"}


class EquipmentLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or EQUIPMENT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.root / "equipment_catalog.json"
        if not self.catalog_path.exists():
            atomic_write_json(self.catalog_path, {"schema_version": 1, "assets": []})

    def catalog(self) -> dict[str, Any]:
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))

    def selected_assets(self, asset_ids: list[str]) -> list[dict[str, Any]]:
        available = {str(item["id"]): item for item in self.catalog().get("assets", [])}
        missing = [asset_id for asset_id in asset_ids if asset_id not in available]
        if missing:
            raise EquipmentLibraryError("Unknown equipment asset IDs: " + ", ".join(missing))
        return [available[asset_id] for asset_id in asset_ids]

    def register_local(self, source_path: Path, asset_id: str, name: str, asset_type: str, slot: str, handedness: str | None = None, primary_socket: str | None = None, secondary_grip: dict[str, Any] | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        source = source_path.expanduser().resolve()
        if not source.is_file() or source.suffix.lower() != ".glb":
            raise EquipmentLibraryError("Equipment source must be an existing GLB file")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", asset_id):
            raise EquipmentLibraryError("asset_id may contain only letters, numbers, '-' and '_'")
        if asset_type not in VALID_TYPES:
            raise EquipmentLibraryError(f"Unsupported equipment type: {asset_type}")
        if asset_type == "WEAPON" and not primary_socket:
            raise EquipmentLibraryError("Weapons require a primary_socket")
        report = validate_glb(source, require_skeleton=asset_type in SKINNED_TYPES)
        if not report.valid:
            raise EquipmentLibraryError("Equipment GLB validation failed: " + "; ".join(report.errors))
        destination = (self.root / asset_id).resolve()
        if self.root.resolve() not in destination.parents or destination.exists():
            raise EquipmentLibraryError(f"Equipment destination is unavailable: {asset_id}")
        destination.mkdir(parents=True)
        try:
            target = destination / "asset.glb"
            shutil.copy2(source, target)
            record = {
                "id": asset_id,
                "name": name,
                "asset_type": asset_type,
                "slot": slot,
                "handedness": handedness,
                "primary_socket": primary_socket,
                "secondary_grip": secondary_grip,
                "tags": tags or [],
                "source_file": str(source),
                "source_sha256": self._sha256(source),
                "asset_path": str(target),
                "validation": report.__dict__,
            }
            atomic_write_json(destination / "equipment.manifest.json", record)
            catalog = self.catalog()
            catalog["assets"] = [item for item in catalog.get("assets", []) if item.get("id") != asset_id] + [record]
            atomic_write_json(self.catalog_path, catalog)
            return record
        except Exception:
            shutil.rmtree(destination)
            raise

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
