from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.cache import clean, inventory
from app.job_store import JobStore
from app.schemas import JobCreateRequest, StageName, StageStatus


class CacheTests(unittest.TestCase):
    def test_inventory_marks_ready_exports_protected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary))
            manifest = store.create(JobCreateRequest())
            manifest.status = "READY"
            manifest.stages[StageName.EXPORT.value].status = StageStatus.READY
            store.save(manifest)
            (Path(temporary) / manifest.job_id / "geometry" / "mesh.glb").write_bytes(b"mesh")
            (Path(temporary) / manifest.job_id / "export" / "unit.glb").write_bytes(b"final")

            item = inventory(store)[0]
            self.assertFalse(item["cleanable"])
            self.assertEqual(item["cache_bytes"], 4)
            self.assertEqual(item["protected_bytes"], 5 + (Path(temporary) / manifest.job_id / "job.json").stat().st_size)

    def test_clean_removes_only_intermediate_files_and_invalidates_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JobStore(root)
            manifest = store.create(JobCreateRequest())
            manifest.status = "FAILED"
            manifest.stages[StageName.GEOMETRY.value].status = StageStatus.READY
            store.save(manifest)
            job_dir = root / manifest.job_id
            (job_dir / "geometry" / "mesh.glb").write_bytes(b"mesh")
            (job_dir / "references" / "original" / "front.png").write_bytes(b"input")
            (job_dir / "export" / "unit.glb").write_bytes(b"final")

            result = clean(store, [manifest.job_id])
            self.assertEqual(result["deleted_bytes"], 4)
            self.assertFalse((job_dir / "geometry" / "mesh.glb").exists())
            self.assertTrue((job_dir / "references" / "original" / "front.png").exists())
            self.assertTrue((job_dir / "export" / "unit.glb").exists())
            cleaned = store.get(manifest.job_id)
            self.assertEqual(cleaned.status, "INVALIDATED")
            self.assertEqual(cleaned.stages[StageName.GEOMETRY.value].status, StageStatus.INVALIDATED)

    def test_clean_skips_running_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary))
            manifest = store.create(JobCreateRequest())
            manifest.status = "RUNNING"
            manifest.stages[StageName.GEOMETRY.value].status = StageStatus.RUNNING
            store.save(manifest)
            result = clean(store, [manifest.job_id])
            self.assertEqual(result["cleaned"], [])
            self.assertEqual(result["skipped"][0]["reason"], "A stage is running")


if __name__ == "__main__":
    unittest.main()
