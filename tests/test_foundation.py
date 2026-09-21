from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.job_store import JobStore
from app.reference_pipeline import assess_reference, preprocess_reference
from app.schemas import JobCreateRequest, StageName, StageStatus


class FoundationTests(unittest.TestCase):
    def test_job_store_creates_persistent_stage_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary))
            manifest = store.create(JobCreateRequest())
            loaded = store.get(manifest.job_id)
            self.assertEqual(loaded.job_id, manifest.job_id)
            self.assertEqual(loaded.stages[StageName.REFERENCES.value].status, StageStatus.PENDING)
            self.assertTrue((Path(temporary) / manifest.job_id / "references" / "original").is_dir())

    def test_reference_preprocessing_preserves_foreground_and_reports_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "front.jpg"
            processed = root / "processed" / "front.png"
            image = Image.new("RGB", (100, 160), "white")
            ImageDraw.Draw(image).rectangle((35, 15, 65, 145), fill="black")
            image.save(source)
            result = preprocess_reference(source, processed, 384)
            quality = assess_reference(processed)
            self.assertEqual(result["processed_size"], [384, 384])
            self.assertGreater(result["alpha_pixels"], 0)
            self.assertIn(quality["level"], {"GOOD", "WARNING"})
            self.assertTrue(processed.is_file())


if __name__ == "__main__":
    unittest.main()
