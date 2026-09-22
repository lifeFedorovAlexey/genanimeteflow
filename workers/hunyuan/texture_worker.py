from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from workers.common.worker_protocol import read_request, write_result


def _run_official_paint(
    request: dict,
    root: Path,
    environment: dict,
    python_executable: str,
    mesh: Path,
    images: list[Path],
    output: Path,
) -> dict:
    """Use Tencent's seam-aware multiview bake as the production path."""
    payload = {
        "mesh_path": str(mesh),
        "images": [str(image) for image in images],
        "output_mesh": str(output),
        "model_id": str(request.get("model_id", "tencent/Hunyuan3D-2")),
        "model_path": os.getenv("HUNYUAN_PAINT_MODEL_PATH", ""),
        "texture_resolution": int(request.get("texture_resolution", 2048)),
        "low_vram_mode": bool(request.get("low_vram_mode", True)),
    }
    completed = subprocess.run(
        [python_executable, "-m", "workers.hunyuan.texture_inference"],
        cwd=root,
        env=environment,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        combined = completed.stdout + "\n" + completed.stderr
        category = "FAILED_OOM" if "out of memory" in combined.lower() else "PROVIDER_ERROR"
        return {"ok": False, "category": category, "error": f"Hunyuan Paint worker exited with code {completed.returncode}", "stdout": completed.stdout, "stderr": completed.stderr}
    try:
        result = _last_json_object(completed.stdout)
    except ValueError:
        return {"ok": False, "category": "WORKER_PROTOCOL", "error": "Hunyuan Paint did not return JSON", "stdout": completed.stdout, "stderr": completed.stderr}
    if not result.get("ok"):
        return result
    output_path = Path(str(result.get("mesh_path", output))).resolve()
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return {"ok": False, "category": "PROVIDER_OUTPUT_INVALID", "error": f"Hunyuan Paint did not produce a non-empty GLB: {output_path}"}

    result.update(
        provider="HunyuanPaintProvider",
        input_view_count=len(images),
        multiview_bake=len(images) > 1,
        texture_cleanup="none",
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    return result


def run(request: dict) -> dict:
    root_value = os.getenv("HUNYUAN_ROOT")
    if not root_value:
        return {"ok": False, "category": "MODEL_MISSING", "error": "HUNYUAN_ROOT is not configured"}
    root = Path(root_value).expanduser().resolve()
    if not (root / "hy3dgen" / "texgen").is_dir():
        return {"ok": False, "category": "MODEL_MISSING", "error": f"Hunyuan texture package is missing under {root}"}
    mesh = Path(str(request.get("mesh_path", ""))).expanduser().resolve()
    image_values = request.get("images") or ([request.get("image")] if request.get("image") else [])
    images = [Path(str(value)).expanduser().resolve() for value in image_values]
    if not mesh.is_file():
        return {"ok": False, "category": "INPUT_MISSING", "error": f"Mesh for texturing was not found: {mesh}"}
    missing = [str(image) for image in images if not image.is_file()]
    if missing:
        return {"ok": False, "category": "INPUT_MISSING", "error": f"Texture references were not found: {', '.join(missing)}"}
    if not images:
        return {"ok": False, "category": "INPUT_MISSING", "error": "At least one texture reference is required"}
    output = Path(str(request.get("output_mesh", ""))).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    python_executable = os.getenv("HUNYUAN_PYTHON") or sys.executable
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(Path(__file__).resolve().parents[2]), str(root), environment.get("PYTHONPATH", "")]))
    # Diffusers may materialize trusted local pipeline modules even when all
    # model weights are already present. Keep that write inside the local
    # Hunyuan checkout instead of an ACL-restricted user cache on Windows.
    job_cache = output.parent.parent.parent / ".cache" / "huggingface"
    cache_root = Path(os.getenv("HUNYUAN_CACHE_ROOT", str(job_cache))).expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "HF_HOME": str(cache_root),
            "HF_MODULES_CACHE": str(cache_root / "modules"),
            "HUGGINGFACE_HUB_CACHE": str(cache_root / "hub"),
            "TRANSFORMERS_CACHE": str(cache_root / "transformers"),
        }
    )
    # A failed Paint run must remain failed, not silently switch to a different
    # unvalidated projection algorithm and report success.
    return _run_official_paint(request, root, environment, python_executable, mesh, images, output)


def _last_json_object(output: str) -> dict:
    for line in reversed(output.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("No JSON object found in worker output")


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
