"""Re-bake captured Hunyuan views without re-running diffusion or downloading weights."""
import argparse
import json
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--capture', required=True)
parser.add_argument('--uv', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--resolution', type=int, default=2048)
parser.add_argument('--pixel-inpaint', action='store_true')
parser.add_argument('--surface-inpaint', action='store_true')
parser.add_argument('--align-texels', action='store_true')
parser.add_argument('--diagnostic-output', help='Save projected color and observed/missing surface coverage without changing the bake')
args = parser.parse_args()
sys.path.insert(0, os.environ['HUNYUAN_ROOT'])
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
import trimesh
from PIL import Image
from hy3dgen.texgen.pipelines import Hunyuan3DPaintPipeline, Hunyuan3DTexGenConfig
from hy3dgen.texgen.differentiable_renderer.mesh_render import MeshRender

capture = Path(args.capture)
if args.uv.endswith('.npz'):
    data = np.load(args.uv)
    mesh = trimesh.Trimesh(vertices=data['vertices'], faces=data['faces'], process=False,
        visual=trimesh.visual.TextureVisuals(uv=data['uv']))
else:
    mesh = trimesh.load(args.uv, force='mesh', process=False)
pipeline = Hunyuan3DPaintPipeline.__new__(Hunyuan3DPaintPipeline)
pipeline.config = Hunyuan3DTexGenConfig('', '', 'hunyuan3d-paint-v2-0-turbo')
pipeline.render = MeshRender(default_resolution=args.resolution, texture_size=args.resolution)
pipeline.render.load_mesh(mesh)
cameras = json.loads((capture / 'cameras.json').read_text())
views = [Image.open(capture / f'view_{i}.png').resize((args.resolution, args.resolution)) for i in range(len(cameras['elevs']))]
texture, mask = pipeline.bake_from_multiview(views, cameras['elevs'], cameras['azims'], cameras['weights'], method='fast')
mask = (mask.squeeze(-1).cpu().numpy() * 255).astype('uint8')
if args.diagnostic_output:
    diagnostic = Path(args.diagnostic_output)
    diagnostic.mkdir(parents=True, exist_ok=True)
    Image.fromarray((texture.cpu().numpy().clip(0, 1)*255).astype('uint8')).save(diagnostic / 'projected.png')
    Image.fromarray(mask).save(diagnostic / 'observed.png')
    # Green is directly observed by a camera; red requires surface filling.
    coverage = np.zeros((*mask.shape, 3), dtype=np.float32)
    coverage[mask > 0] = [.1, .8, .1]
    coverage[mask == 0] = [.9, .05, .05]
    pipeline.render.set_texture(torch.from_numpy(coverage).to(texture.device))
    diagnostic_mesh = pipeline.render.save_mesh()
    diagnostic_mesh.visual.material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=diagnostic_mesh.visual.material.image, metallicFactor=0., roughnessFactor=1.)
    diagnostic_mesh.export(diagnostic / 'coverage.glb')
if args.surface_inpaint:
    from workers.hunyuan.surface_inpaint import surface_inpaint
    texture = surface_inpaint(pipeline.render, texture, mask)
elif args.pixel_inpaint:
    import cv2
    pixels = (texture.cpu().numpy().clip(0,1)*255).astype('uint8')
    texture = torch.from_numpy(cv2.inpaint(pixels, 255-mask, 3, cv2.INPAINT_NS)/255).float().cuda()
else:
    texture = pipeline.texture_inpaint(texture, mask)
pipeline.render.set_texture(texture)
result = pipeline.render.save_mesh()
if args.align_texels:
    result.visual.uv = (result.visual.uv * (args.resolution - 1) + .5) / args.resolution
# Paint predicts base color, not a metallic/roughness PBR map.
result.visual.material = trimesh.visual.material.PBRMaterial(
    baseColorTexture=result.visual.material.image, metallicFactor=0.0, roughnessFactor=.8)
result.export(args.output)
print('REBAKE_COMPLETE', args.output, flush=True)
