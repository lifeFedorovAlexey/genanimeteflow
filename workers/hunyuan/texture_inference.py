"""Run Tencent's Hunyuan3D-Paint pipeline in the isolated model environment."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _allow_official_local_pipeline_code() -> None:
    """Allow Tencent's checked-out diffusers custom pipeline with modern diffusers."""
    from diffusers import DiffusionPipeline

    original = DiffusionPipeline.from_pretrained

    def trusted_from_pretrained(cls, *args, **kwargs):
        kwargs.setdefault("trust_remote_code", True)
        return original.__func__(cls, *args, **kwargs)

    DiffusionPipeline.from_pretrained = classmethod(trusted_from_pretrained)


def run(request: dict) -> dict:
    official_root = Path(os.environ.get("HUNYUAN_ROOT", ".")).expanduser().resolve()
    if str(official_root) not in sys.path:
        sys.path.insert(0, str(official_root))
    import torch
    import trimesh
    from PIL import Image
    _allow_official_local_pipeline_code()
    from hy3dgen.texgen import Hunyuan3DPaintPipeline

    if not torch.cuda.is_available():
        return {"ok": False, "category": "CUDA_UNAVAILABLE", "error": "Hunyuan Paint Python cannot access CUDA"}
    loaded = trimesh.load(request["mesh_path"], force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [item for item in loaded.geometry.values() if isinstance(item, trimesh.Trimesh)]
        if not meshes:
            return {"ok": False, "category": "INPUT_INVALID", "error": "Input GLB contains no triangle mesh"}
        loaded = trimesh.util.concatenate(meshes)
    pipeline = Hunyuan3DPaintPipeline.from_pretrained(request["model_path"] or request["model_id"])
    if request.get("low_vram_mode") and hasattr(pipeline, "enable_model_cpu_offload"):
        pipeline.enable_model_cpu_offload()
    started = time.perf_counter()
    textured = pipeline(loaded, image=Image.open(request["image"]).convert("RGBA"))
    output_path = Path(request["output_mesh"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    textured.export(output_path)
    if hasattr(torch.cuda, "empty_cache"):
        torch.cuda.empty_cache()
    return {"ok": True, "mesh_path": str(output_path), "duration_seconds": time.perf_counter() - started, "settings": request}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.loads(sys.stdin.read())), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "category": "PROVIDER_ERROR", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
