from __future__ import annotations

import csv
import io
import subprocess
import threading
import time
from typing import Any


class VramMonitor:
    def __init__(self, interval_seconds: float = 0.25) -> None:
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[dict[str, float]] = []

    @staticmethod
    def snapshot() -> dict[str, Any] | None:
        try:
            import pynvml  # type: ignore
        except ImportError:
            pynvml = None
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                return {"used_bytes": float(memory.used), "total_bytes": float(memory.total), "source": "nvml"}
            except pynvml.NVMLError:
                return None
            finally:
                try:
                    pynvml.nvmlShutdown()
                except pynvml.NVMLError:
                    _ = True
        try:
            completed = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        rows = list(csv.reader(io.StringIO(completed.stdout)))
        if not rows or len(rows[0]) < 2:
            return None
        try:
            return {"used_bytes": float(rows[0][0].strip()) * 1024 * 1024, "total_bytes": float(rows[0][1].strip()) * 1024 * 1024, "source": "nvidia-smi"}
        except ValueError:
            return None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("VRAM monitor is already running")
        self._stop.clear()
        self._samples = []
        self._thread = threading.Thread(target=self._sample_loop, name="character-factory-vram", daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 4))
        self._thread = None
        before = self._samples[0] if self._samples else None
        after = self._samples[-1] if self._samples else self.snapshot()
        peak = max(self._samples, key=lambda item: item["used_bytes"]) if self._samples else None
        return {"before": before, "peak": peak, "after": after, "sample_count": len(self._samples)}

    def _sample_loop(self) -> None:
        while not self._stop.is_set():
            sample = self.snapshot()
            if sample is not None:
                self._samples.append(sample)
            time.sleep(self.interval_seconds)
