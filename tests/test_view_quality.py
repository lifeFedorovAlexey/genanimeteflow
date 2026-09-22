from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.view_quality import DINOV3_MODEL_ID, dinov3_model_path, dinov3_runtime
from workers.dinov3.worker import _cosine


class ViewQualityTests(unittest.TestCase):
    def test_runtime_requires_both_local_snapshot_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("app.view_quality.Path.home", return_value=root), patch.dict(os.environ, {"DINOV3_MODEL_PATH": str(root), "DINOV3_PYTHON": "python"}, clear=False):
                self.assertIsNone(dinov3_model_path())
                self.assertFalse(dinov3_runtime()["available"])
            (root / "config.json").write_text("{}", encoding="utf-8")
            (root / "model.safetensors").write_bytes(b"weights")
            with patch("app.view_quality.Path.home", return_value=root), patch.dict(os.environ, {"DINOV3_MODEL_PATH": str(root), "DINOV3_PYTHON": "python"}, clear=False):
                runtime = dinov3_runtime()
                self.assertTrue(runtime["available"])
                self.assertEqual(runtime["model_id"], DINOV3_MODEL_ID)

    def test_cosine_is_one_for_identical_vectors(self) -> None:
        self.assertAlmostEqual(_cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0)

    def test_cosine_rejects_non_finite_vectors(self) -> None:
        self.assertEqual(_cosine([float("nan")], [1.0]), 0.0)


if __name__ == "__main__":
    unittest.main()
