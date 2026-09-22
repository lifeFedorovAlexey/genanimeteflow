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
from workers.hunyuan.texture_inference import _prepare_paint_image
from app.runner import choose_geometry_provider


class HunyuanWorkerTests(unittest.TestCase):
    def test_auto_prefers_spar3d_for_single_front_when_available(self) -> None:
        provider, fallback = choose_geometry_provider("AUTO", 1, multiview_ready=True, single_view_ready=True, spar3d_ready=True)
        self.assertEqual(provider, "spar3d")
        self.assertIsNone(fallback)

    def test_auto_records_real_single_view_fallback_reason(self) -> None:
        provider, fallback = choose_geometry_provider("AUTO", 1, multiview_ready=True, single_view_ready=True, spar3d_ready=False)
        self.assertEqual(provider, "hunyuan-single")
        self.assertIn("SPAR3D", fallback or "")

    def test_auto_does_not_feed_multiple_views_to_single_view_provider(self) -> None:
        provider, fallback = choose_geometry_provider("AUTO", 4, multiview_ready=False, single_view_ready=True, spar3d_ready=False)
        self.assertEqual(provider, "unavailable")
        self.assertIn("single-view", fallback or "")

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

    def test_paint_input_composites_transparency_on_white(self) -> None:
        from PIL import Image

        source = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
        source.putpixel((0, 0), (255, 0, 0, 255))

        prepared = _prepare_paint_image(source)

        self.assertEqual(prepared.mode, "RGB")
        self.assertEqual(prepared.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(prepared.getpixel((1, 0)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
