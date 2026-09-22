"""Project the supplied reference views onto a generated mesh without hallucinated dirt.

This is intentionally deterministic. Hunyuan Paint is useful for unseen areas,
but its generated atlas can introduce speckles on stylised characters. For a
four-view character, a normal-weighted projection is a safer first material:
each surface point receives colour from the views that actually face it and
overlapping views are blended before export.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_image(path: Path):
    import numpy as np
    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("RGBA")
        return np.asarray(image, dtype=np.float32) / 255.0


def _project(vertices, normals, bounds, view: str, image):
    import numpy as np

    minimum, maximum = bounds
    extent = np.maximum(maximum - minimum, 1e-6)
    # Hunyuan GLB uses X as width, Y as up and Z as depth.  The former
    # projector treated Z as up, which made every sampled pixel come from a
    # wrong body region and was the source of the washed-out face/hair.
    if view == "front":
        u = (vertices[:, 0] - minimum[0]) / extent[0]
        v = 1.0 - (vertices[:, 1] - minimum[1]) / extent[1]
        facing = np.maximum(normals[:, 2], 0.0)
    elif view == "back":
        u = 1.0 - (vertices[:, 0] - minimum[0]) / extent[0]
        v = 1.0 - (vertices[:, 1] - minimum[1]) / extent[1]
        facing = np.maximum(normals[:, 2] * -1.0, 0.0)
    elif view == "left":
        u = (vertices[:, 2] - minimum[2]) / extent[2]
        v = 1.0 - (vertices[:, 1] - minimum[1]) / extent[1]
        facing = np.maximum(normals[:, 0] * -1.0, 0.0)
    else:  # right
        u = 1.0 - (vertices[:, 2] - minimum[2]) / extent[2]
        v = 1.0 - (vertices[:, 1] - minimum[1]) / extent[1]
        facing = np.maximum(normals[:, 0], 0.0)

    height, width = image.shape[:2]
    x = np.clip(np.rint(u * (width - 1)).astype(np.int32), 0, width - 1)
    y = np.clip(np.rint(v * (height - 1)).astype(np.int32), 0, height - 1)
    pixels = image[y, x]
    # Ignore anti-aliased transparent fringes. Their dark RGB values are a
    # common source of the black/brown speckling visible on generated GLBs.
    opaque = pixels[:, 3] > (128.0 / 255.0)

    confidence = np.where(opaque, pixels[:, 3], 0.0)
    orientation = np.power(facing, 0.75)
    # Keep front/back ownership stable across rounded limbs and shoulders.
    # Side references are narrower and should only take over where the mesh
    # genuinely turns away from the main camera, not because of tiny normal
    # fluctuations on a front-facing arm or leg.
    if view in {"front", "back"}:
        orientation = 0.18 + (0.82 * orientation)
    weights = np.where(opaque, orientation * confidence, 0.0)
    return pixels[:, :3], weights, opaque, orientation


def run(request: dict) -> dict:
    import numpy as np
    import trimesh

    mesh_path = Path(request["mesh_path"]).resolve()
    output_path = Path(request["output_mesh"]).resolve()
    image_paths = [Path(value).resolve() for value in request["images"]]
    views = request.get("views") or ["front", "left", "back", "right"][: len(image_paths)]
    loaded = trimesh.load(mesh_path, force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        meshes = [item for item in loaded.geometry.values() if isinstance(item, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("Input GLB contains no triangle mesh")
        loaded = trimesh.util.concatenate(meshes)
    mesh = loaded
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    normals = np.asarray(mesh.vertex_normals, dtype=np.float32)
    bounds = (vertices.min(axis=0), vertices.max(axis=0))
    projected_pixels = []
    projected_weights = []
    projected_orientation = []
    used_views = []
    for view, image_path in zip(views, image_paths):
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        pixels, weights, _valid, orientation = _project(vertices, normals, bounds, view, _load_image(image_path))
        projected_pixels.append(pixels)
        projected_weights.append(weights)
        projected_orientation.append(orientation)
        used_views.append(view)

    # Select one view per vertex instead of averaging front/side/back colours.
    # Hard ownership prevents muddy seams when the generated mesh differs a
    # few pixels from the four reference silhouettes.
    pixels_stack = np.stack(projected_pixels, axis=0)
    weights_stack = np.stack(projected_weights, axis=0)
    orientation_stack = np.stack(projected_orientation, axis=0)
    owners = np.argmax(orientation_stack, axis=0)
    owner_indices = np.arange(len(vertices))
    chosen_weights = weights_stack[owners, owner_indices]
    vertex_colours = pixels_stack[owners, np.arange(len(vertices))]
    uncovered = chosen_weights <= 1e-5
    if np.any(uncovered):
        # Fill only vertices with no trustworthy image sample from nearby
        # painted geometry. This keeps colour boundaries on the 3D surface
        # and avoids both transparent-background speckles and 2D smear bands.
        try:
            from scipy.spatial import cKDTree

            painted = ~uncovered
            if np.any(painted):
                tree = cKDTree(vertices[painted])
                distances, indices = tree.query(vertices[uncovered], k=min(8, int(painted.sum())))
                if np.ndim(indices) == 1:
                    indices = indices[:, None]
                nearby = vertex_colours[painted][indices]
                influence = 1.0 / np.maximum(distances, 1e-4)
                filled = (nearby * influence[..., None]).sum(axis=1) / influence.sum(axis=1)[..., None]
                vertex_colours[uncovered] = filled.astype(np.float32)
            else:
                vertex_colours[uncovered] = 0.5
        except ImportError:
            vertex_colours[uncovered] = 0.5
    vertex_colours = np.clip(vertex_colours, 0.0, 1.0)
    rgba = np.concatenate([vertex_colours, np.ones((len(vertices), 1), dtype=np.float32)], axis=1)
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=(rgba * 255.0).astype(np.uint8))
    mesh.visual.material = trimesh.visual.material.PBRMaterial(
        baseColorFactor=[255, 255, 255, 255], metallicFactor=0.0, roughnessFactor=0.78
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(output_path)
    return {
        "ok": True,
        "mesh_path": str(output_path),
        "provider": "MultiViewProjectionProvider",
        "input_view_count": len(used_views),
        "views": used_views,
        "vertex_color_count": len(vertices),
    }


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.loads(sys.stdin.read())), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "category": "PROJECTION_ERROR", "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
