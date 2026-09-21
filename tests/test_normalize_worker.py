from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


class NormalizeWorkerTests(unittest.TestCase):
    def test_reports_missing_blender_without_claiming_normalization(self) -> None:
        environment = os.environ.copy()
        environment.pop("BLENDER_PATH", None)
        completed = subprocess.run(
            [sys.executable, "-m", "workers.blender.normalize_worker"],
            input=json.dumps({"source_motion": "motion.glb", "target_rig": "rig.glb", "output_mesh": "normalized.glb", "action": "Idle"}),
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "BLENDER_MISSING")
