from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.model_registry import ModelRegistry


class ModelRegistryTests(unittest.TestCase):
    def _registry(self, folder: Path) -> ModelRegistry:
        registry_path = folder / "registry.json"
        registry_path.write_text(json.dumps({"models": [{"id": "spar3d", "provider": "Spar3DProvider", "repository": "https://example.invalid/spar3d", "model_id": "example/spar3d", "license": "test", "worker_root_env": "TEST_SPAR3D_ROOT", "python_env": "TEST_SPAR3D_PYTHON"}]}), encoding="utf-8")
        return ModelRegistry(registry_path)

    def test_missing_environment_reports_the_required_checkout_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            status = self._registry(Path(directory)).status()[0]
        self.assertFalse(status["installed"])
        self.assertEqual(status["reason"], "Set TEST_SPAR3D_ROOT to the official checkout")

    def test_checkout_requires_a_cuda_ready_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "spar3d"
            root.mkdir()
            (root / "run.py").write_text("", encoding="utf-8")
            python = root / "python.exe"
            python.write_text("", encoding="utf-8")
            with patch.dict(os.environ, {"TEST_SPAR3D_ROOT": str(root), "TEST_SPAR3D_PYTHON": str(python)}, clear=True), patch.object(ModelRegistry, "_runtime_status", return_value={"ready": True, "reason": None}):
                status = self._registry(Path(directory)).status()[0]
        self.assertTrue(status["checkout_ready"])
        self.assertTrue(status["runtime_ready"])
        self.assertTrue(status["installed"])

    def test_gated_model_access_does_not_report_installed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "spar3d"
            root.mkdir()
            (root / "run.py").write_text("", encoding="utf-8")
            python = root / "python.exe"
            python.write_text("", encoding="utf-8")
            result = subprocess.CompletedProcess([], 0, "cuda=True\nmodel_access=http_401\n", "")
            environment = {"TEST_SPAR3D_ROOT": str(root), "TEST_SPAR3D_PYTHON": str(python)}
            with patch.dict(os.environ, environment, clear=True), patch("app.model_registry.subprocess.run", return_value=result):
                status = self._registry(Path(directory)).status()[0]
        self.assertFalse(status["installed"])
        self.assertFalse(status["runtime_ready"])
        self.assertIn("model terms", status["reason"])


if __name__ == "__main__":
    unittest.main()
