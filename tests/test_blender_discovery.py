from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.blender_discovery import blender_path


class BlenderDiscoveryTests(unittest.TestCase):
    def test_configured_executable_wins_when_it_exists(self) -> None:
        with patch.dict(os.environ, {"BLENDER_PATH": r"C:\Blender\blender.exe"}, clear=False), patch("app.blender_discovery.Path.is_file", return_value=True):
            self.assertEqual(blender_path(), r"C:\Blender\blender.exe")

    def test_windows_registry_install_location_is_supported(self) -> None:
        installed = Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe")
        with patch.dict(os.environ, {}, clear=True), patch("app.blender_discovery.sys.platform", "win32"), patch("app.blender_discovery.shutil.which", return_value=None), patch("app.blender_discovery._windows_registry_paths", return_value=[installed]), patch("app.blender_discovery.Path.is_file", return_value=True):
            self.assertEqual(blender_path(), str(installed))


if __name__ == "__main__":
    unittest.main()
