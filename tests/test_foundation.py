from __future__ import annotations

import tempfile
import unittest
import sys
import asyncio
from pathlib import Path

from PIL import Image, ImageDraw

from app.job_store import JobStore
from app.model_registry import ModelRegistry
from app.process_manager import ProcessManager, WorkerFailure
from app.pipeline_graph import downstream
from app.runner import SingleGpuQueue
from app.reference_pipeline import assess_reference, preprocess_reference
from app.schemas import JobCreateRequest, StageName, StageStatus


class FoundationTests(unittest.TestCase):
    def test_single_gpu_queue_serializes_operations(self) -> None:
        async def scenario() -> int:
            queue = SingleGpuQueue()
            active = 0
            peak = 0
            guard = asyncio.Lock()

            async def operation() -> None:
                nonlocal active, peak
                async with guard:
                    active += 1
                    peak = max(peak, active)
                await asyncio.sleep(0)
                async with guard:
                    active -= 1

            await asyncio.gather(queue.run(operation), queue.run(operation))
            return peak

        self.assertEqual(asyncio.run(scenario()), 1)

    def test_model_registry_reports_uninstalled_workers_without_claiming_availability(self) -> None:
        statuses = ModelRegistry().status()
        self.assertTrue(any(item["id"] == "spar3d" for item in statuses))
        self.assertTrue(all("reason" in item for item in statuses))

    def test_worker_protocol_rejects_non_json_worker_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(WorkerFailure) as context:
                ProcessManager().run_json_worker([sys.executable, "-c", "print('not json')"], {}, Path(temporary), {}, Path(temporary) / "worker.log")
            self.assertEqual(context.exception.category, "WORKER_PROTOCOL")

    def test_job_store_creates_persistent_stage_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary))
            manifest = store.create(JobCreateRequest())
            loaded = store.get(manifest.job_id)
            self.assertEqual(loaded.job_id, manifest.job_id)
            self.assertEqual(loaded.stages[StageName.REFERENCES.value].status, StageStatus.PENDING)
            self.assertTrue((Path(temporary) / manifest.job_id / "references" / "original").is_dir())

    def test_dependency_graph_invalidates_only_downstream_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary))
            manifest = store.create(JobCreateRequest())
            for stage in manifest.stages.values():
                stage.status = StageStatus.READY
            store.invalidate_from(manifest, StageName.GEOMETRY)
            self.assertEqual(manifest.stages[StageName.GEOMETRY.value].status, StageStatus.READY)
            self.assertEqual(manifest.stages[StageName.RETOPOLOGY.value].status, StageStatus.INVALIDATED)
            self.assertEqual(downstream(StageName.GEOMETRY)[-1], StageName.EXPORT)

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
            self.assertLess(result["foreground_ratio"], 0.95)
            self.assertIn(quality["level"], {"GOOD", "WARNING"})
            self.assertTrue(processed.is_file())


if __name__ == "__main__":
    unittest.main()
