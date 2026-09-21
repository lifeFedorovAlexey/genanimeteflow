from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from workers.common.worker_protocol import read_request, write_result


SUPPORTED_VIEWS = ("front", "left", "back")


def run(request: dict) -> dict:
    root_value = os.getenv("HUNYUAN_ROOT")
    if not root_value:
        return {"ok": False, "category": "MODEL_MISSING", "error": "HUNYUAN_ROOT is not configured"}
    root = Path(root_value).expanduser().resolve()
    marker = root / "hy3dgen" / "shapegen"
    if not marker.is_dir():
        return {"ok": False, "category": "MODEL_MISSING", "error": f"Official Hunyuan checkout is missing hy3dgen/shapegen: {root}"}
    images = request.get("images")
    if not isinstance(images, dict) or not images.get("front"):
        return {"ok": False, "category": "INPUT_MISSING", "error": "Hunyuan multiview requires a processed FRONT image"}
    selected: dict[str, str] = {}
    for view in SUPPORTED_VIEWS:
        value = images.get(view)
        if value:
            path = Path(str(value)).expanduser().resolve()
            if not path.is_file():
                return {"ok": False, "category": "INPUT_MISSING", "error": f"Processed {view} reference was not found: {path}"}
            selected[view] = str(path)
    if not selected:
        return {"ok": False, "category": "INPUT_MISSING", "error": "Hunyuan requires a processed FRONT image"}
    # The released Hunyuan2mv API documents front/left/back. Do not silently
    # pretend that RIGHT was consumed; report it to the orchestration layer.
    ignored_views = sorted(set(images) - set(selected))
    output_dir = Path(str(request.get("output_dir", ""))).expanduser().resolve()
    if not str(output_dir):
        return {"ok": False, "category": "WORKER_REQUEST", "error": "output_dir is required"}
    output_dir.mkdir(parents=True, exist_ok=True)
    python_executable = os.getenv("HUNYUAN_PYTHON") or sys.executable
    command = [python_executable, "-m", "workers.hunyuan.inference"]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(Path(__file__).resolve().parents[2]), str(root), environment.get("PYTHONPATH", "")]))
    completed = subprocess.run(
        command,
        cwd=root,
        input=_request_for_inference(request, selected, output_dir),
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        combined = completed.stdout + "\n" + completed.stderr
        category = "FAILED_OOM" if "out of memory" in combined.lower() or "cuda out of memory" in combined.lower() else "PROVIDER_ERROR"
        return {"ok": False, "category": category, "error": f"Hunyuan3D worker exited with code {completed.returncode}", "stdout": completed.stdout, "stderr": completed.stderr}
    try:
        result = __import__("json").loads(completed.stdout)
    except ValueError:
        return {"ok": False, "category": "WORKER_PROTOCOL", "error": "Hunyuan inference did not return JSON", "stdout": completed.stdout, "stderr": completed.stderr}
    if not result.get("ok"):
        return result
    mesh_path = Path(str(result.get("mesh_path", ""))).resolve()
    if not mesh_path.is_file() or mesh_path.stat().st_size == 0:
        return {"ok": False, "category": "PROVIDER_OUTPUT_INVALID", "error": f"Hunyuan did not produce a non-empty GLB: {mesh_path}", "stdout": completed.stdout, "stderr": completed.stderr}
    provider = "HunyuanMultiviewProvider" if str(request.get("settings", {}).get("model_id", "")).endswith("2mv") else "HunyuanSingleViewProvider"
    result.update(provider=provider, ignored_views=ignored_views, stdout=completed.stdout, stderr=completed.stderr)
    return result


def _request_for_inference(request: dict, images: dict[str, str], output_dir: Path) -> str:
    import json

    settings = request.get("settings") if isinstance(request.get("settings"), dict) else {}
    payload = {
        "images": images,
        "output_dir": str(output_dir),
        "model_id": str(settings.get("model_id", "tencent/Hunyuan3D-2mv")),
        "model_path": os.getenv("HUNYUAN_SHAPE_MODEL_PATH", "") if "2mv" in str(settings.get("model_id", "")) else os.getenv("HUNYUAN_SINGLE_MODEL_PATH", ""),
        "subfolder": str(settings.get("subfolder", "hunyuan3d-dit-v2-mv")),
        "steps": int(settings.get("steps", 30)),
        "octree_resolution": int(settings.get("octree_resolution", 380)),
        "num_chunks": int(settings.get("num_chunks", 20000)),
        "seed": int(settings.get("seed", 42)),
        "low_vram_mode": bool(settings.get("low_vram_mode", True)),
    }
    return json.dumps(payload)


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
