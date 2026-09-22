from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BlenderWorkerTests(unittest.TestCase):
    def test_reports_missing_blender_without_claiming_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.glb"
            source.write_bytes(b"source")
            environment = os.environ.copy()
            environment.pop("BLENDER_PATH", None)
            completed = subprocess.run([sys.executable, "-m", "workers.blender.worker"], input=json.dumps({"source_mesh": str(source), "output_mesh": str(Path(directory) / "out.glb"), "mode": "TRIANGLE"}), text=True, capture_output=True, env=environment, check=False)
            result = json.loads(completed.stdout)
            self.assertFalse(result["ok"])
            self.assertEqual(result["category"], "BLENDER_MISSING")

    def test_keep_source_copies_the_original_without_blender(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.glb"
            output = root / "keep.glb"
            source.write_bytes(b"real glb bytes")
            environment = os.environ.copy()
            environment.pop("BLENDER_PATH", None)
            completed = subprocess.run([sys.executable, "-m", "workers.blender.worker"], input=json.dumps({"source_mesh": str(source), "output_mesh": str(output), "mode": "KEEP_SOURCE"}), text=True, capture_output=True, env=environment, check=False)
            result = json.loads(completed.stdout)
            self.assertTrue(result["ok"])
            self.assertEqual(output.read_bytes(), source.read_bytes())
