"""Run Tencent's Hunyuan3D-Paint pipeline in the isolated model environment."""
from __future__ import annotations

import json
import os
import sys
import time
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


def _allow_official_local_pipeline_code() -> None:
    """Allow Tencent's checked-out diffusers custom pipeline with modern diffusers."""
    from diffusers import DiffusionPipeline

    original = DiffusionPipeline.from_pretrained

    def trusted_from_pretrained(cls, *args, **kwargs):
        kwargs.setdefault("trust_remote_code", True)
        return original.__func__(cls, *args, **kwargs)

    DiffusionPipeline.from_pretrained = classmethod(trusted_from_pretrained)


def _prepare_paint_image(image):
    """Keep alpha so Tencent's recenter_image can align the reference."""
    return image.convert("RGBA")


def _prepare_mesh_uv(mesh_path: str, output_dir: Path):
    import numpy as np
    import trimesh

    blender = os.environ.get("BLENDER_PATH", "")
    if not blender or not Path(blender).is_file():
        raise RuntimeError("Blender is required to prepare the Paint UV atlas")
    script = Path(__file__).resolve().parents[2] / "scripts" / "prepare_paint_uv.py"
    with tempfile.TemporaryDirectory(prefix="paint-uv-", dir=output_dir) as directory:
        target = Path(directory) / "mesh.npz"
        completed = subprocess.run(
            [blender, "--background", "--python-exit-code", "1", "--python", str(script), "--",
             "--input", str(mesh_path), "--output", str(target),
             "--merge-small-charts", "--remove-floaters"],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode or not target.is_file():
            raise RuntimeError(f"Paint UV preparation failed: {completed.stdout}\n{completed.stderr}")
        with np.load(target) as data:
            mesh = trimesh.Trimesh(vertices=data["vertices"], faces=data["faces"], process=False,
                visual=trimesh.visual.TextureVisuals(uv=data["uv"]))
    # Smooth shading must be continuous across UV seams without welding UVs.
    points, inverse = np.unique(mesh.vertices, axis=0, return_inverse=True)
    normals = trimesh.geometry.mean_vertex_normals(len(points), inverse[mesh.faces], mesh.face_normals)
    mesh.vertex_normals = normals[inverse]
    return mesh


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
    from hy3dgen.texgen import pipelines as paint_module
    from workers.hunyuan.surface_inpaint import surface_inpaint

    if not torch.cuda.is_available():
        return {"ok": False, "category": "CUDA_UNAVAILABLE", "error": "Hunyuan Paint Python cannot access CUDA"}
    started = time.perf_counter()
    output_path = Path(request["output_mesh"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    loaded = _prepare_mesh_uv(request["mesh_path"], output_path.parent)
    pipeline = Hunyuan3DPaintPipeline.from_pretrained(request["model_path"] or request["model_id"])
    _configure_texture_resolution(pipeline, int(request.get("texture_resolution", 2048)))
    # Tencent's Paint wrapper is a custom pipeline, not a diffusers Pipeline;
    # its similarly named offload helper expects a ``components`` mapping that
    # does not exist. Device placement is handled by the official pipeline.
    image_paths = request.get("images") or [request["image"]]
    paint_images = []
    for image_path in image_paths:
        with Image.open(image_path) as source_image:
            paint_images.append(_prepare_paint_image(source_image))
    # Keep Tencent's delight, multiview synthesis and visibility-weighted bake.
    # Preserve the prepared atlas and fill unobserved texels on the surface;
    # unrelated atlas islands must not donate colors to one another.
    pipeline.texture_inpaint = lambda texture, mask: surface_inpaint(pipeline.render, texture, mask)
    with patch.object(paint_module, "mesh_uv_wrap", lambda mesh: mesh):
        textured = pipeline(loaded, image=paint_images)
    textured.visual.material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=textured.visual.material.image, metallicFactor=0.0, roughnessFactor=.8)
    textured.export(output_path)
    if hasattr(torch.cuda, "empty_cache"):
        torch.cuda.empty_cache()
    return {"ok": True, "mesh_path": str(output_path), "duration_seconds": time.perf_counter() - started, "input_view_count": len(paint_images), "multiview_bake": len(paint_images) > 1,
            "uv_method": "blender_angle_based_merged_charts", "inpaint_method": "surface_nearest_then_uv_padding",
            "bake_resolution": pipeline.config.texture_size, "settings": request}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.loads(sys.stdin.read())), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "category": "PROVIDER_ERROR", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
