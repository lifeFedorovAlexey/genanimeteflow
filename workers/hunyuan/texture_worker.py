from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from workers.common.worker_protocol import read_request, write_result


def run(request: dict) -> dict:
    root_value = os.getenv("HUNYUAN_ROOT")
    if not root_value:
        return {"ok": False, "category": "MODEL_MISSING", "error": "HUNYUAN_ROOT is not configured"}
    root = Path(root_value).expanduser().resolve()
    if not (root / "hy3dgen" / "texgen").is_dir():
        return {"ok": False, "category": "MODEL_MISSING", "error": f"Hunyuan texture package is missing under {root}"}
    mesh = Path(str(request.get("mesh_path", ""))).expanduser().resolve()
    image = Path(str(request.get("image", ""))).expanduser().resolve()
    if not mesh.is_file():
        return {"ok": False, "category": "INPUT_MISSING", "error": f"Mesh for texturing was not found: {mesh}"}
    if not image.is_file():
        return {"ok": False, "category": "INPUT_MISSING", "error": f"Front reference for texturing was not found: {image}"}
    output = Path(str(request.get("output_mesh", ""))).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    python_executable = os.getenv("HUNYUAN_PYTHON") or sys.executable
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(Path(__file__).resolve().parents[2]), str(root), environment.get("PYTHONPATH", "")]))
    payload = {
        "mesh_path": str(mesh),
        "image": str(image),
        "output_mesh": str(output),
        "model_id": str(request.get("model_id", "tencent/Hunyuan3D-2")),
        "texture_resolution": int(request.get("texture_resolution", 1024)),
        "low_vram_mode": bool(request.get("low_vram_mode", True)),
    }
    completed = subprocess.run([python_executable, "-m", "workers.hunyuan.texture_inference"], cwd=root, env=environment, input=json.dumps(payload), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        combined = completed.stdout + "\n" + completed.stderr
        category = "FAILED_OOM" if "out of memory" in combined.lower() else "PROVIDER_ERROR"
        return {"ok": False, "category": category, "error": f"Hunyuan Paint worker exited with code {completed.returncode}", "stdout": completed.stdout, "stderr": completed.stderr}
    try:
        result = json.loads(completed.stdout)
    except ValueError:
        return {"ok": False, "category": "WORKER_PROTOCOL", "error": "Hunyuan Paint did not return JSON", "stdout": completed.stdout, "stderr": completed.stderr}
    if not result.get("ok"):
        return result
    output_path = Path(str(result.get("mesh_path", output))).resolve()
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return {"ok": False, "category": "PROVIDER_OUTPUT_INVALID", "error": f"Hunyuan Paint did not produce a non-empty GLB: {output_path}"}
    result.update(provider="HunyuanPaintProvider", stdout=completed.stdout, stderr=completed.stderr)
    return result


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
