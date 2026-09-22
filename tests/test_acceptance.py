from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.acceptance import validate_job
from app.job_store import JobStore
from app.schemas import JobCreateRequest, ReferenceSlot, StageName, StageStatus


class AcceptanceTests(unittest.TestCase):
    def _ready_manifest(self, root: Path):
        store = JobStore(root)
        manifest = store.create(JobCreateRequest())
        for stage in (StageName.REFERENCES, StageName.GEOMETRY, StageName.TEXTURES, StageName.RETOPOLOGY, StageName.RIG, StageName.MOTIONS, StageName.EXPORT, StageName.EQUIPMENT, StageName.CLOTHING, StageName.IK):
            manifest.stages[stage.value].status = StageStatus.READY
        manifest.references["front"] = ReferenceSlot(view="front", required=True, original_path="references/original/front.png")
        job_dir = root / manifest.job_id
        (job_dir / "references/original/front.png").write_bytes(b"input")
        (job_dir / "export/unit.glb").write_bytes(b"glb")
        (job_dir / "export/unit.fbx").write_bytes(b"fbx")
        (job_dir / "export/unit.manifest.json").write_text("{}", encoding="utf-8")
        manifest.stages[StageName.EXPORT.value].result = {
            "glb_path": "export/unit.glb",
            "fbx_path": "export/unit.fbx",
            "manifest_path": "export/unit.manifest.json",
            "selected_actions": ["idle"],
            "roundtrip": {
                "animation_count": 1,
                "glb": {"valid": True, "errors": [], "texture_count": 1, "skin_count": 1, "vertex_count": 12},
                "rig": {"valid": True, "joint_count": 2},
            },
        }
        manifest.equipment_assets = ["rifle"]
        manifest.clothing_assets = ["vest"]
        manifest.stages[StageName.IK.value].result = {"targets": [{"id": "hand_l"}], "constraints": [{"type": "IK"}]}
        manifest.status = "READY"
        store.save(manifest)
        return manifest, job_dir

    def test_acceptance_passes_for_complete_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, job_dir = self._ready_manifest(Path(temporary))
            result = validate_job(manifest, job_dir)
            self.assertTrue(result["valid"])
            self.assertEqual(result["metrics"]["animations"], 1)

    def test_acceptance_fails_when_final_glb_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, job_dir = self._ready_manifest(Path(temporary))
            (job_dir / "export/unit.glb").unlink()
            result = validate_job(manifest, job_dir)
            self.assertFalse(result["valid"])
            self.assertFalse(next(check for check in result["checks"] if check["id"] == "export:glb")["passed"])


if __name__ == "__main__":
    unittest.main()
