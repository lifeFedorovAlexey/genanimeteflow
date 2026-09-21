from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from PIL import Image

from app import main
from app.job_store import JobStore
from app.schemas import JobCreateRequest, ReferenceSlot, StageStatus


class ReferenceUploadTests(unittest.TestCase):
    def upload(self, job_id: str):
        image = BytesIO()
        Image.new("RGB", (8, 8), "blue").save(image, "PNG")
        image.seek(0)
        return asyncio.run(main.upload_reference(job_id, "front", UploadFile(
            file=image, filename="front.png", headers=Headers({"content-type": "image/png"}),
        )))

    def test_replacement_invalidates_ready_results_and_blocks_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            job = store.create(JobCreateRequest())
            source = store.job_dir(job.job_id) / "references/original/front.png"
            source.write_bytes(b"old source")
            mesh = store.job_dir(job.job_id) / "geometry/mesh.glb"
            mesh.write_bytes(b"previous output kept for inspection")
            job.references["front"] = ReferenceSlot(view="front", original_path="references/original/front.png", processed_path="references/processed/front.png")
            for record in job.stages.values():
                record.status = StageStatus.READY
            store.save(job)
            with patch.object(main, "store", store):
                updated = self.upload(job.job_id)
                self.assertTrue(all(record.status == StageStatus.INVALIDATED for record in updated.stages.values()))
                self.assertIsNone(updated.references["front"].processed_path)
                self.assertEqual(store.get(job.job_id).status, "INVALIDATED")
                self.assertTrue(mesh.exists())
                with self.assertRaises(HTTPException) as error:
                    asyncio.run(main.run_stage(job.job_id, "geometry"))
                self.assertEqual(error.exception.status_code, 409)

    def test_running_job_rejects_upload_without_overwriting_source(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            job = store.create(JobCreateRequest())
            job.stages["geometry"].status = StageStatus.RUNNING
            store.save(job)
            source = store.job_dir(job.job_id) / "references/original/front.png"
            source.write_bytes(b"source used by worker")
            with patch.object(main, "store", store):
                with self.assertRaises(HTTPException) as error:
                    self.upload(job.job_id)
                self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(source.read_bytes(), b"source used by worker")


if __name__ == "__main__":
    unittest.main()
