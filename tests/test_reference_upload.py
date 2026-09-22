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
from PIL import ImageDraw

from app import main
from app.job_store import JobStore
from app.schemas import JobCreateRequest, JobSettingsRequest, ReferenceSlot, RetopologySettingsRequest, StageStatus
from app.reference_pipeline import assess_reference


class ReferenceUploadTests(unittest.TestCase):
    def test_reference_quality_reports_full_body_and_t_pose_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "front.png"
            image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((56, 10, 72, 118), fill=(255, 255, 255, 255))
            draw.rectangle((18, 35, 110, 44), fill=(255, 255, 255, 255))
            draw.rectangle((50, 82, 59, 121), fill=(255, 255, 255, 255))
            draw.rectangle((69, 82, 78, 121), fill=(255, 255, 255, 255))
            image.save(path)

            quality = assess_reference(path)

            self.assertEqual(quality["level"], "GOOD")
            self.assertGreater(quality["silhouette"]["upper_body_span_ratio"], 0.9)
            self.assertTrue(quality["silhouette"]["left_side_foreground"])
            self.assertTrue(quality["silhouette"]["right_side_foreground"])

    def test_reference_quality_warns_when_arms_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "front.png"
            image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((55, 10, 73, 121), fill=(255, 255, 255, 255))
            image.save(path)

            quality = assess_reference(path)

            self.assertEqual(quality["level"], "WARNING")
            self.assertTrue(any("T-pose" in warning for warning in quality["warnings"]))

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

    def test_retopology_settings_are_persisted_and_invalidate_downstream(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            job = store.create(JobCreateRequest())
            for record in job.stages.values():
                record.status = StageStatus.READY
            store.save(job)
            with patch.object(main, "store", store):
                updated = main.set_retopology_settings(job.job_id, RetopologySettingsRequest(mode="QUAD", target_faces=24000))
            self.assertEqual(updated.retopology_mode, "QUAD")
            self.assertEqual(updated.retopology_target_faces, 24000)
            self.assertEqual(updated.stages["retopology"].status, StageStatus.INVALIDATED)
            self.assertEqual(updated.stages["rig"].status, StageStatus.INVALIDATED)

    def test_quality_settings_invalidate_only_the_affected_pipeline_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            job = store.create(JobCreateRequest())
            for record in job.stages.values():
                record.status = StageStatus.READY
            store.save(job)
            with patch.object(main, "store", store):
                updated = main.set_job_settings(job.job_id, JobSettingsRequest(texture_resolution=512))
            self.assertEqual(updated.texture_resolution, 512)
            self.assertEqual(updated.stages["references"].status, StageStatus.READY)
            self.assertEqual(updated.stages["geometry"].status, StageStatus.READY)
            self.assertEqual(updated.stages["textures"].status, StageStatus.INVALIDATED)
            self.assertEqual(updated.stages["rig"].status, StageStatus.INVALIDATED)

            with patch.object(main, "store", store):
                updated = main.set_job_settings(job.job_id, JobSettingsRequest(profile="MAX", resolution=1024))
            self.assertEqual(updated.profile, "MAX")
            self.assertEqual(updated.resolution, 1024)
            self.assertEqual(updated.stages["references"].status, StageStatus.INVALIDATED)
            self.assertEqual(updated.stages["geometry"].status, StageStatus.INVALIDATED)

    def test_quality_settings_reject_changes_during_running_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            job = store.create(JobCreateRequest())
            job.stages["geometry"].status = StageStatus.RUNNING
            store.save(job)
            with patch.object(main, "store", store):
                with self.assertRaises(HTTPException) as error:
                    main.set_job_settings(job.job_id, JobSettingsRequest(profile="MAX"))
            self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
