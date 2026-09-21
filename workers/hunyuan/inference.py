"""Run the official Hunyuan3D-2mv pipeline in its isolated Python environment."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def run(request: dict) -> dict:
    root = Path(__file__).resolve().parents[2]
    official_root = Path(os.environ.get("HUNYUAN_ROOT", ".")).expanduser().resolve()
    if str(official_root) not in sys.path:
        sys.path.insert(0, str(official_root))
    import torch
    from PIL import Image
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    if not torch.cuda.is_available():
        return {"ok": False, "category": "CUDA_UNAVAILABLE", "error": "Hunyuan Python cannot access CUDA"}
    image_paths = request["images"]
    images = {view: Image.open(path).convert("RGBA") for view, path in image_paths.items()}
    model_id = request["model_id"]
    subfolder = request["subfolder"]
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        model_id,
        subfolder=subfolder,
        use_safetensors=True,
        device="cuda",
    )
    if request.get("low_vram_mode") and hasattr(pipeline, "enable_model_cpu_offload"):
        pipeline.enable_model_cpu_offload()
    generator = torch.Generator(device="cuda").manual_seed(int(request.get("seed", 42)))
    started = time.perf_counter()
    mesh = pipeline(
        image=images,
        num_inference_steps=int(request.get("steps", 30)),
        octree_resolution=int(request.get("octree_resolution", 380)),
        num_chunks=int(request.get("num_chunks", 20000)),
        generator=generator,
        output_type="trimesh",
    )[0]
    output_dir = Path(request["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "mesh.glb"
    mesh.export(output_path)
    if hasattr(torch.cuda, "empty_cache"):
        torch.cuda.empty_cache()
    return {"ok": True, "mesh_path": str(output_path), "duration_seconds": time.perf_counter() - started, "settings": request}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.loads(sys.stdin.read())), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "category": "PROVIDER_ERROR", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
