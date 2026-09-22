from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from app import main
from app.schemas import AnimationGraphRequest, JobManifest, StageName, StageRecord, StageStatus


class AnimationGraphApiTests(unittest.TestCase):
    def test_endpoint_uses_normalized_job_clips(self) -> None:
        now = datetime.now(UTC)
        manifest = JobManifest(
            job_id="unit-graph",
            created_at=now,
            updated_at=now,
            stages={StageName.MOTIONS.value: StageRecord(name=StageName.MOTIONS, status=StageStatus.READY, result={"clips": [{"clip_id": "motion:idle", "action": "Idle", "category": "idle", "duration": 1.0, "worker": {"normalized_action": "normalized_Idle"}}]})},
        )
        with patch.object(main, "get_job", return_value=manifest):
            result = main.evaluate_animation_graph("unit-graph", AnimationGraphRequest())
        self.assertEqual(result["clip_id"], "motion:idle")
        self.assertEqual(result["action_name"], "normalized_Idle")
        self.assertEqual(result["state"], "idle")

    def test_endpoint_preserves_camel_case_root_motion_metadata(self) -> None:
        now = datetime.now(UTC)
        manifest = JobManifest(
            job_id="unit-root-motion",
            created_at=now,
            updated_at=now,
            stages={StageName.MOTIONS.value: StageRecord(name=StageName.MOTIONS, status=StageStatus.READY, result={"clips": [{"clip_id": "motion:walk", "action": "Walk_RM", "category": "walk", "duration": 1.0, "rootMotion": True, "worker": {"normalized_action": "normalized_Walk_RM"}}]})},
        )
        with patch.object(main, "get_job", return_value=manifest):
            result = main.evaluate_animation_graph("unit-root-motion", AnimationGraphRequest(speed=1.0))
        self.assertTrue(result["root_motion"])
        self.assertEqual(result["root_motion_mode"], "apply")
