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
    """Keep the cutout in the format expected by Tencent's official pipeline.

    Hunyuan Paint's own ``recenter_image`` crops RGBA references and restores
    a controlled border before its delight and multiview stages. Converting
    these images to opaque RGB here bypassed that alignment step and made the
    diffusion model treat the unused canvas as character pixels.
    """
    from PIL import Image

    return image.convert("RGBA")


def _configure_texture_resolution(pipeline, resolution: int):
    """Apply the requested texture size to Tencent's renderer and bake path."""
    if resolution not in {512, 1024, 2048}:
        raise ValueError("Hunyuan Paint texture resolution must be 512, 1024, or 2048")
    pipeline.config.render_size = resolution
    pipeline.config.texture_size = resolution
    pipeline.render.set_default_render_resolution(resolution)
    pipeline.render.set_default_texture_resolution(resolution)
    # MeshRender computes this once in __init__; keep its resolution-dependent
    # unreliable-kernel threshold consistent after changing the configuration.
    pipeline.render.bake_unreliable_kernel_size = max(1, int((2 / 512) * resolution))
    return pipeline


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
    _configure_texture_resolution(pipeline, int(request.get("texture_resolution", 1024)))
    # Tencent's Paint wrapper is a custom pipeline, not a diffusers Pipeline;
    # its similarly named offload helper expects a ``components`` mapping that
    # does not exist. Device placement is handled by the official pipeline.
    started = time.perf_counter()
    image_paths = request.get("images") or [request["image"]]
    paint_images = []
    for image_path in image_paths:
        with Image.open(image_path) as source_image:
            paint_images.append(_prepare_paint_image(source_image))
    # Tencent's official Paint pipeline accepts a list of reference views. It
    # renders its own normal/position cameras, synthesizes missing views, then
    # bakes them with weighted seam-aware blending. Passing only FRONT here was
    # the reason four-view jobs still produced stretched, dirty atlases.
    textured = pipeline(loaded, image=paint_images)
    output_path = Path(request["output_mesh"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    textured.export(output_path)
    if hasattr(torch.cuda, "empty_cache"):
        torch.cuda.empty_cache()
    return {"ok": True, "mesh_path": str(output_path), "duration_seconds": time.perf_counter() - started, "input_view_count": len(paint_images), "multiview_bake": len(paint_images) > 1, "settings": request}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.loads(sys.stdin.read())), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "category": "PROVIDER_ERROR", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
