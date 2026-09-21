from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


class UniRigWorkerTests(unittest.TestCase):
    def test_reports_missing_official_checkout(self) -> None:
        environment = os.environ.copy()
        environment.pop("UNIRIG_ROOT", None)
        completed = subprocess.run([sys.executable, "-m", "workers.unirig.worker"], input=json.dumps({"source_mesh": "missing.glb", "output_dir": "out"}), text=True, capture_output=True, env=environment, check=False)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "MODEL_MISSING")
