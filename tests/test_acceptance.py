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
        manifest.stages[StageName.MOTIONS.value].result = {
            "clips": [
                {"clip_id": "idle", "action": "Idle_Loop", "category": "idle", "duration": 1.0, "worker": {"normalized_action": "normalized_Idle_Loop"}},
                {"clip_id": "walk", "action": "Walk_Loop", "category": "walk", "duration": 1.0, "worker": {"normalized_action": "normalized_Walk_Loop"}},
                {"clip_id": "sprint", "action": "Sprint_Loop", "category": "run", "duration": 1.0, "worker": {"normalized_action": "normalized_Sprint_Loop"}},
                {"clip_id": "crouch", "action": "Crouch_Fwd_Loop", "category": "crouch", "duration": 1.0, "worker": {"normalized_action": "normalized_Crouch_Fwd_Loop"}},
                {"clip_id": "jump-start", "action": "Jump_Start", "category": "jump", "duration": 1.0, "worker": {"normalized_action": "normalized_Jump_Start"}},
                {"clip_id": "jump-air", "action": "Jump_Loop", "category": "jump", "duration": 1.0, "worker": {"normalized_action": "normalized_Jump_Loop"}},
                {"clip_id": "jump-land", "action": "Jump_Land", "category": "jump", "duration": 1.0, "worker": {"normalized_action": "normalized_Jump_Land"}},
                {"clip_id": "attack", "action": "Melee_Hook", "category": "attack", "duration": 1.0, "worker": {"normalized_action": "normalized_Melee_Hook"}},
                {"clip_id": "hit", "action": "Hit_Knockback", "category": "attack", "duration": 1.0, "worker": {"normalized_action": "normalized_Hit_Knockback"}},
                {"clip_id": "death", "action": "Death01", "category": "death", "duration": 1.0, "worker": {"normalized_action": "normalized_Death01"}},
            ],
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

    def test_acceptance_rejects_incomplete_animation_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, job_dir = self._ready_manifest(Path(temporary))
            manifest.stages[StageName.MOTIONS.value].result["clips"] = [
                clip for clip in manifest.stages[StageName.MOTIONS.value].result["clips"]
                if clip["category"] in {"idle", "walk", "run", "attack"}
            ]
            result = validate_job(manifest, job_dir)
            graph_check = next(check for check in result["checks"] if check["id"] == "graph:states")
            self.assertFalse(result["valid"])
            self.assertFalse(graph_check["passed"])
            self.assertIn("jump_start", graph_check["detail"])

    def test_full_acceptance_rejects_single_view_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, job_dir = self._ready_manifest(Path(temporary))
            result = validate_job(manifest, job_dir, require_full_acceptance=True)
            self.assertFalse(result["valid"])
            self.assertFalse(next(check for check in result["checks"] if check["id"] == "full:four-views")["passed"])

    def test_full_acceptance_requires_multiview_and_quality_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, job_dir = self._ready_manifest(Path(temporary))
            for view in ("left", "back", "right"):
                manifest.references[view] = ReferenceSlot(view=view, original_path=f"references/original/{view}.png", processed_path=f"references/processed/{view}.png", quality={"level": "GOOD"})
                (job_dir / f"references/original/{view}.png").write_bytes(b"input")
            manifest.references["front"].processed_path = "references/processed/front.png"
            manifest.references["front"].quality = {"level": "GOOD"}
            manifest.actual_provider = "HunyuanMultiviewProvider"
            manifest.stages[StageName.GEOMETRY.value].result = {"provider_views": ["front", "left", "back", "right"]}
            manifest.stages[StageName.REFERENCES.value].result = {"view_consistency": {"level": "GOOD"}}
            manifest.equipment_assets = ["cc0-fantasy-sword", "cc0-lightning-rifle"]
            manifest.clothing_assets = ["utility-vest"]

            result = validate_job(manifest, job_dir, require_full_acceptance=True)

            self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
