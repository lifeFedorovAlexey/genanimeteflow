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


def _prepare_paint_image(image):
    """Give Hunyuan Paint an opaque RGB reference, never a cutout alpha mask.

    The reference preprocessor intentionally writes transparent PNGs for shape
    reconstruction. Paint interprets those transparent pixels as image input,
    which can turn the cutout boundary into white blocks and dark speckles.
    Compositing over the reference's neutral white background keeps that alpha
    representation local to geometry generation and gives Paint a real image.
    """
    from PIL import Image

    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(background, rgba).convert("RGB")


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
    # Tencent's Paint wrapper is a custom pipeline, not a diffusers Pipeline;
    # its similarly named offload helper expects a ``components`` mapping that
    # does not exist. Device placement is handled by the official pipeline.
    started = time.perf_counter()
    with Image.open(request["image"]) as source_image:
        paint_image = _prepare_paint_image(source_image)
    textured = pipeline(loaded, image=paint_image)
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
