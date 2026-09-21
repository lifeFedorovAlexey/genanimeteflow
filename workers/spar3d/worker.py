from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from workers.common.worker_protocol import read_request, write_result


def run(request: dict) -> dict:
    root_value = os.getenv("SPAR3D_ROOT")
    if not root_value:
        return {"ok": False, "category": "MODEL_MISSING", "error": "SPAR3D_ROOT is not configured"}
    root = Path(root_value).expanduser().resolve()
    script = root / "run.py"
    if not script.is_file():
        return {"ok": False, "category": "MODEL_MISSING", "error": f"Official SPAR3D run.py was not found at {script}"}
    image = Path(str(request["image"])).expanduser().resolve()
    if not image.is_file():
        return {"ok": False, "category": "INPUT_MISSING", "error": f"Input reference was not found: {image}"}
    output_dir = Path(str(request["output_dir"])).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = request.get("settings", {})
    python_executable = os.getenv("SPAR3D_PYTHON") or sys.executable
    command = [python_executable, str(script), str(image), "--output-dir", str(output_dir), "--texture-resolution", str(int(settings.get("texture_resolution", 1024)))]
    if settings.get("low_vram_mode", False):
        command.append("--low-vram-mode")
    remesh = str(settings.get("remesh", "none")).lower()
    command.extend(["--remesh_option", remesh])
    if remesh != "none" and settings.get("target_count") is not None:
        command.extend(["--reduction_count_type", "faces", "--target_count", str(int(settings["target_count"]))])
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    output_mesh = output_dir / "0" / "mesh.glb"
    if completed.returncode != 0:
        combined = completed.stdout + "\n" + completed.stderr
        category = "FAILED_OOM" if "out of memory" in combined.lower() else "PROVIDER_ERROR"
        return {"ok": False, "category": category, "error": f"SPAR3D exited with code {completed.returncode}", "stdout": completed.stdout, "stderr": completed.stderr}
    if not output_mesh.is_file() or output_mesh.stat().st_size == 0:
        return {"ok": False, "category": "PROVIDER_OUTPUT_INVALID", "error": f"Official SPAR3D did not produce a non-empty mesh at {output_mesh}", "stdout": completed.stdout, "stderr": completed.stderr}
    return {"ok": True, "provider": "Spar3DProvider", "mesh_path": str(output_mesh), "stdout": completed.stdout, "stderr": completed.stderr, "settings": settings}


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
