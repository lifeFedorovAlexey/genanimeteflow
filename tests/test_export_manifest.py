from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from app.export_manifest import build_unit_manifest
from app.schemas import JobManifest, ReferenceSlot, StageName, StageRecord, StageStatus


class ExportManifestTests(unittest.TestCase):
    def test_manifest_contains_provenance_validation_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_dir = Path(directory)
            now = datetime.now(UTC)
            job = JobManifest(
                job_id="unit-1",
                created_at=now,
                updated_at=now,
                actual_provider="Spar3DProvider",
                references={"front": ReferenceSlot(view="front", original_path="references/original/front.png")},
                stages={
                    StageName.GEOMETRY.value: StageRecord(name=StageName.GEOMETRY, result={"settings": {"remesh": "none"}}),
                    StageName.TEXTURES.value: StageRecord(name=StageName.TEXTURES, result={"images": [{"path": "textures/source/albedo.png"}]}),
                    StageName.RETOPOLOGY.value: StageRecord(name=StageName.RETOPOLOGY, result={"target_faces": 30000}),
                    StageName.RIG.value: StageRecord(name=StageName.RIG, status=StageStatus.READY, result={"validation": {"vertex_count": 12, "face_count": 20, "material_count": 1, "joint_count": 4}}),
                },
                export_actions=["Idle"],
            )
            manifest = build_unit_manifest(job, job_dir, job_dir / "export" / "unit.glb", job_dir / "export" / "unit.fbx", {"animation_count": 1})

        self.assertEqual(manifest["geometry_provider"], "Spar3DProvider")
        self.assertEqual(manifest["vertices"], 12)
        self.assertEqual(manifest["bones"], 4)
        self.assertEqual(manifest["animations"], ["Idle"])
        self.assertEqual(manifest["files"]["manifest"], "export/unit.manifest.json")
        self.assertEqual(manifest["validation"]["glb_roundtrip"]["animation_count"], 1)

