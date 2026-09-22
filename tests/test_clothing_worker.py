from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


class ClothingWorkerTests(unittest.TestCase):
    def test_reports_missing_blender_without_claiming_transfer(self) -> None:
        environment = os.environ.copy()
        environment.pop("BLENDER_PATH", None)
        completed = subprocess.run([sys.executable, "-m", "workers.blender.clothing_worker"], input=json.dumps({"target_rig": "missing.glb", "output_mesh": "out.glb", "assets": []}), text=True, capture_output=True, env=environment, check=False)
        self.assertIn('"ok": false', completed.stdout.lower())
