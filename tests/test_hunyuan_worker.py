from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workers.hunyuan.worker import run
from workers.hunyuan.texture_worker import run as run_texture


class HunyuanWorkerTests(unittest.TestCase):
    def test_reports_missing_official_checkout(self) -> None:
        with patch.dict(os.environ, {"HUNYUAN_ROOT": ""}, clear=False):
            result = run({"images": {"front": "front.png", "left": "left.png"}, "output_dir": "out"})
        self.assertEqual(result["category"], "MODEL_MISSING")

    def test_requires_two_real_views(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hunyuan"
            (root / "hy3dgen" / "shapegen").mkdir(parents=True)
            image = root / "front.png"
            image.write_bytes(b"input")
            with patch.dict(os.environ, {"HUNYUAN_ROOT": str(root)}, clear=False):
                result = run({"images": {"front": str(image)}, "output_dir": str(root / "out")})
        self.assertEqual(result["category"], "INPUT_UNSUPPORTED")

    def test_missing_view_file_is_not_silently_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hunyuan"
            (root / "hy3dgen" / "shapegen").mkdir(parents=True)
            image = root / "front.png"
            image.write_bytes(b"input")
            with patch.dict(os.environ, {"HUNYUAN_ROOT": str(root)}, clear=False):
                result = run({"images": {"front": str(image), "back": str(root / "missing.png")}, "output_dir": str(root / "out")})
        self.assertEqual(result["category"], "INPUT_MISSING")

    def test_texture_worker_requires_real_mesh_and_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hunyuan"
            (root / "hy3dgen" / "texgen").mkdir(parents=True)
            with patch.dict(os.environ, {"HUNYUAN_ROOT": str(root)}, clear=False):
                result = run_texture({"mesh_path": str(root / "missing.glb"), "image": str(root / "missing.png"), "output_mesh": str(root / "out.glb")})
        self.assertEqual(result["category"], "INPUT_MISSING")


if __name__ == "__main__":
    unittest.main()
