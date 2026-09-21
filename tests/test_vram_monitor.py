from __future__ import annotations

import unittest
from unittest.mock import patch

from app.vram_monitor import VramMonitor


class VramMonitorTests(unittest.TestCase):
    def test_snapshot_uses_nvidia_smi_when_nvml_is_unavailable(self) -> None:
        completed = type("Completed", (), {"returncode": 0, "stdout": "128, 12288\n", "stderr": ""})()
        with patch("subprocess.run", return_value=completed):
            with patch.dict("sys.modules", {"pynvml": None}):
                sample = VramMonitor.snapshot()
        self.assertIsNotNone(sample)
        self.assertEqual(sample["source"], "nvidia-smi")
        self.assertEqual(sample["total_bytes"], 12288 * 1024 * 1024)
