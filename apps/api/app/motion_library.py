from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .config import REPO_ROOT
from .storage import atomic_write_json
from tools.validation.glb import GlbReader


class MotionLibraryError(RuntimeError):
    """A source archive or catalog entry failed validation."""


class MotionLibrary:
    def __init__(self, catalog_path: Path | None = None, install_root: Path | None = None) -> None:
        self.catalog_path = catalog_path or REPO_ROOT / "motions" / "motion_catalog.json"
        self.install_root = install_root or REPO_ROOT / "motions" / "installed"
        self.install_root.mkdir(parents=True, exist_ok=True)

    def catalog(self) -> dict[str, Any]:
        with self.catalog_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def clips(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for library in self.catalog().get("libraries", []):
            for clip in library.get("clips", []):
                name = str(clip.get("name", ""))
                normalized_name = name.lower()
                enriched = {**clip, "category": clip.get("category") or self._category_for_name(name), "loop": bool(clip.get("loop")) or "_loop" in normalized_name or normalized_name.endswith("loop"), "rootMotion": bool(clip.get("rootMotion")) or "_rm" in normalized_name or normalized_name.endswith("rm"), "library_id": library.get("id"), "license": library.get("license"), "allowed_for_commercial_use": library.get("allowed_for_commercial_use", False)}
                result[str(clip["id"])] = enriched
        return result

    def selected_clips(self, clip_ids: list[str]) -> list[dict[str, Any]]:
        available = self.clips()
        missing = [clip_id for clip_id in clip_ids if clip_id not in available]
        if missing:
            raise MotionLibraryError("Unknown motion clip IDs: " + ", ".join(missing))
        return [available[clip_id] for clip_id in clip_ids]

    def register_local(self, source_path: Path, library_id: str, source_id: str, license_text: str, allowed_for_commercial_use: bool) -> dict[str, Any]:
        source_path = source_path.expanduser().resolve()
        if not source_path.is_file():
            raise MotionLibraryError(f"Motion source file does not exist: {source_path}")
        if not library_id.replace("-", "").replace("_", "").isalnum():
            raise MotionLibraryError("library_id may contain only letters, numbers, '-' and '_'")
        target = (self.install_root / library_id).resolve()
        if self.install_root.resolve() not in target.parents:
            raise MotionLibraryError("Invalid motion library destination")
        if target.exists():
            raise MotionLibraryError(f"Motion library already exists: {library_id}")
        target.mkdir(parents=True, exist_ok=False)
        try:
            if source_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(source_path) as archive:
                    self._safe_extract(archive, target)
            else:
                shutil.copy2(source_path, target / source_path.name)
            files = [path for path in target.rglob("*") if path.is_file()]
            clips = self._scan_files(files, library_id)
            record = {"id": library_id, "source_id": source_id, "license": license_text, "allowed_for_commercial_use": allowed_for_commercial_use, "source_archive": str(source_path), "source_sha256": self._sha256(source_path), "installed_path": str(target), "files": [str(path.relative_to(target)) for path in files], "clips": clips, "validation": {"file_count": len(files), "clip_count": len(clips), "invalid_count": 0}}
            catalog = self.catalog()
            catalog["libraries"] = [item for item in catalog.get("libraries", []) if item.get("id") != library_id] + [record]
            atomic_write_json(self.catalog_path, catalog)
            return record
        except Exception:
            shutil.rmtree(target)
            raise

    @staticmethod
    def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
        for member in archive.infolist():
            destination = (target / member.filename).resolve()
            if target.resolve() not in destination.parents and destination != target.resolve():
                raise MotionLibraryError(f"Archive contains an unsafe path: {member.filename}")
        archive.extractall(target)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _scan_files(self, files: list[Path], library_id: str) -> list[dict[str, Any]]:
        clips: list[dict[str, Any]] = []
        for path in files:
            if path.suffix.lower() not in {".glb", ".gltf"}:
                continue
            if path.suffix.lower() != ".glb":
                clips.append({"id": f"{library_id}:{path.stem}", "name": path.stem, "source_file": str(path), "format": path.suffix.lower().lstrip("."), "validation": "metadata-only"})
                continue
            reader = GlbReader(path)
            reader.read()
            for index, animation in enumerate(reader.document.get("animations", [])):
                name = str(animation.get("name") or f"clip_{index}")
                duration, sample_count = self._animation_duration(reader, animation)
                normalized_name = name.lower()
                clips.append({"id": f"{library_id}:{path.stem}:{index}", "name": name, "source_file": str(path), "format": "glb", "duration": duration, "fps": round((sample_count - 1) / duration, 3) if duration and sample_count > 1 else None, "loop": "_loop" in normalized_name or normalized_name.endswith("loop"), "rootMotion": "_rm" in normalized_name or normalized_name.endswith("rm"), "requiredEquipmentType": None, "normalized": False})
        return clips

    @staticmethod
    def _category_for_name(name: str) -> str:
        normalized = name.lower().replace("-", "_").replace(" ", "_")
        if any(token in normalized for token in ("idle", "tpose")):
            return "idle"
        if any(token in normalized for token in ("walk", "locomotion")):
            return "walk"
        if any(token in normalized for token in ("run", "sprint")):
            return "run"
        if any(token in normalized for token in ("jump", "climb")):
            return "jump"
        if any(token in normalized for token in ("melee", "sword", "shield", "attack", "throw", "hit")):
            return "attack"
        if any(token in normalized for token in ("crouch", "slide")):
            return "crouch"
        if any(token in normalized for token in ("dead", "death", "die")):
            return "death"
        if any(token in normalized for token in ("farm", "chop", "consume", "interact")):
            return "interact"
        return "other"

    @staticmethod
    def _animation_duration(reader: GlbReader, animation: dict[str, Any]) -> tuple[float | None, int]:
        durations: list[float] = []
        sample_count = 0
        for sampler in animation.get("samplers", []):
            input_accessor = sampler.get("input")
            if input_accessor is None:
                continue
            values = reader.accessor_values(int(input_accessor))
            sample_count = max(sample_count, len(values))
            durations.extend(float(value[0]) for value in values if value)
        return (max(durations) if durations else None), sample_count
