from __future__ import annotations

import os
import json
import subprocess
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

    def test_accepts_one_front_view_for_single_view_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hunyuan"
            (root / "hy3dgen" / "shapegen").mkdir(parents=True)
            image = root / "front.png"
            image.write_bytes(b"input")
            with patch.dict(os.environ, {"HUNYUAN_ROOT": str(root)}, clear=False):
                result = run({"images": {"front": str(image)}, "output_dir": str(root / "out")})
        self.assertEqual(result["category"], "PROVIDER_ERROR")

    def test_missing_view_file_is_not_silently_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hunyuan"
            (root / "hy3dgen" / "shapegen").mkdir(parents=True)
            image = root / "front.png"
            image.write_bytes(b"input")
            with patch.dict(os.environ, {"HUNYUAN_ROOT": str(root)}, clear=False):
                result = run({"images": {"front": str(image), "back": str(root / "missing.png")}, "output_dir": str(root / "out")})
        self.assertEqual(result["category"], "INPUT_MISSING")

    def test_passes_right_view_to_official_multiview_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hunyuan"
            (root / "hy3dgen" / "shapegen").mkdir(parents=True)
            images = {}
            for view in ("front", "left", "back", "right"):
                path = root / f"{view}.png"
                path.write_bytes(b"input")
                images[view] = str(path)
            output_dir = root / "out"
            mesh_path = output_dir / "mesh.glb"

            def fake_run(*args, **kwargs):
                output_dir.mkdir(parents=True, exist_ok=True)
                mesh_path.write_bytes(b"mesh")
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"ok": True, "mesh_path": str(mesh_path)}) + "\n", stderr="")

            with patch.dict(os.environ, {"HUNYUAN_ROOT": str(root)}, clear=False), patch("workers.hunyuan.worker.subprocess.run", side_effect=fake_run) as mocked:
                result = run({"images": images, "output_dir": str(output_dir), "settings": {"model_id": "tencent/Hunyuan3D-2mv"}})

        payload = json.loads(mocked.call_args.kwargs["input"])
        self.assertEqual(set(payload["images"]), {"front", "left", "back", "right"})
        self.assertEqual(result["ignored_views"], [])

    def test_texture_worker_requires_real_mesh_and_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hunyuan"
            (root / "hy3dgen" / "texgen").mkdir(parents=True)
            with patch.dict(os.environ, {"HUNYUAN_ROOT": str(root)}, clear=False):
                result = run_texture({"mesh_path": str(root / "missing.glb"), "image": str(root / "missing.png"), "output_mesh": str(root / "out.glb")})
        self.assertEqual(result["category"], "INPUT_MISSING")


if __name__ == "__main__":
    unittest.main()
