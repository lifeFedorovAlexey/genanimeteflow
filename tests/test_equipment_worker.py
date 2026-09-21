from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


class EquipmentWorkerTests(unittest.TestCase):
    def test_reports_missing_blender_without_claiming_attachment(self) -> None:
        environment = os.environ.copy()
        environment.pop("BLENDER_PATH", None)
        completed = subprocess.run(
            [sys.executable, "-m", "workers.blender.equipment_worker"],
            input=json.dumps({"target_rig": "rig.glb", "output_mesh": "attached.glb", "assets": [{"id": "sword", "asset_path": "sword.glb", "primary_socket": "hand_r"}]}),
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "BLENDER_MISSING")
