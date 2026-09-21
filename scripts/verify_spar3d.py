"""Offline installation check: full imports, CUDA kernels, UV unwrap and CLI."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--check-model-access", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    os.environ["NO_ALBUMENTATIONS_UPDATE"] = "1"
    sys.path.insert(0, str(root))

    import torch
    import trimesh
    from texture_baker import TextureBaker
    from uv_unwrapper import Unwrapper
    from transparent_background import Remover  # noqa: F401
    from spar3d.system import SPAR3D  # noqa: F401
    from spar3d.models.mesh import QUAD_REMESH_AVAILABLE, TRIANGLE_REMESH_AVAILABLE

    assert QUAD_REMESH_AVAILABLE and TRIANGLE_REMESH_AVAILABLE, "Remeshing modules are missing"

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in this Python environment")
    baker = TextureBaker()
    uv = torch.tensor([[0.1, 0.1], [0.9, 0.1], [0.1, 0.9]], device="cuda")
    faces = torch.tensor([[0, 1, 2]], dtype=torch.int32, device="cuda")
    rast = baker.rasterize(uv, faces, 32)
    mask = baker.get_mask(rast)
    colors = torch.ones((3, 3), device="cuda")
    baked = baker.interpolate(colors, rast, faces)
    torch.cuda.synchronize()
    assert mask.any().item(), "CUDA rasterizer produced an empty texture"
    assert baked.shape == (32, 32, 3) and torch.isfinite(baked).all().item()
    torch.testing.assert_close(baked[mask], torch.ones_like(baked[mask]))
    print(f"CUDA texture bake OK: {torch.cuda.get_device_name(0)}, torch {torch.__version__}", flush=True)

    mesh = trimesh.creation.icosphere(subdivisions=1)
    positions = torch.tensor(mesh.vertices.copy(), dtype=torch.float32)
    normals = torch.tensor(mesh.vertex_normals.copy(), dtype=torch.float32)
    triangles = torch.tensor(mesh.faces.copy(), dtype=torch.int64)
    coords, indices = Unwrapper()(positions, normals, triangles, 0.02)
    assert coords.numel() and torch.isfinite(coords).all().item()
    assert indices.numel() == triangles.numel()
    print("Native UV unwrap OK", flush=True)

    completed = subprocess.run([sys.executable, str(root / "run.py"), "--help"],
                               cwd=root, capture_output=True, text=True, timeout=60)
    if completed.returncode:
        raise RuntimeError(completed.stderr or completed.stdout)
    assert "--pretrained-model" in completed.stdout
    print("Official run.py --help OK (model weights are checked separately)", flush=True)
    if args.check_model_access:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url
        from huggingface_hub.utils import HfHubHTTPError
        try:
            metadata = get_hf_file_metadata(
                hf_hub_url("stabilityai/stable-point-aware-3d", "model.safetensors"), timeout=20)
        except HfHubHTTPError as error:
            # Do not dump request headers or credentials into diagnostic logs.
            print(f"Model access: {type(error).__name__}, HTTP {error.response.status_code}")
            print("Accept the model access terms on Hugging Face, then run huggingface-cli login locally.")
            raise SystemExit(2) from None
        print(f"Model access OK; weights size: {metadata.size} bytes")


if __name__ == "__main__":
    main()
