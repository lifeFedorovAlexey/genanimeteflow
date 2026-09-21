from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


class BlenderWorkerTests(unittest.TestCase):
    def test_reports_missing_blender_without_claiming_success(self) -> None:
        environment = os.environ.copy()
        environment.pop("BLENDER_PATH", None)
        completed = subprocess.run([sys.executable, "-m", "workers.blender.worker"], input=json.dumps({"source_mesh": "missing.glb", "output_mesh": "out.glb"}), text=True, capture_output=True, env=environment, check=False)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "BLENDER_MISSING")
