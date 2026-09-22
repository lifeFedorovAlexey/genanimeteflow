"""Capture Paint's real intermediate outputs for reproducible visual diagnosis.

Run with the Hunyuan Python environment; does not modify job manifests or inputs.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--resolution', type=int, default=2048)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    job, output = Path(args.job).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = job / '.cache' / 'huggingface'
    for key, value in {'HF_HOME': cache, 'HF_MODULES_CACHE': cache / 'modules',
                       'HUGGINGFACE_HUB_CACHE': cache / 'hub', 'TRANSFORMERS_CACHE': cache / 'transformers'}.items():
        os.environ[key] = str(value)
    sys.path[:0] = [str(root), os.environ['HUNYUAN_ROOT']]
    from workers.hunyuan.texture_inference import _allow_official_local_pipeline_code, _configure_texture_resolution
    _allow_official_local_pipeline_code()
    import numpy as np
    import trimesh
    from PIL import Image
    from hy3dgen.texgen import Hunyuan3DPaintPipeline
    pipeline = Hunyuan3DPaintPipeline.from_pretrained(os.environ['HUNYUAN_PAINT_MODEL_PATH'])
    _configure_texture_resolution(pipeline, args.resolution)
    original_bake = pipeline.bake_from_multiview
    original_inpaint = pipeline.texture_inpaint

    def bake(views, elevs, azims, weights, **kwargs):
        for i, view in enumerate(views):
            view.save(output / f'view_{i}.png')
        (output / 'cameras.json').write_text(json.dumps(dict(elevs=elevs, azims=azims, weights=weights)))
        pipeline.render.mesh_copy.export(output / 'unwrapped.glb')
        texture, mask = original_bake(views, elevs, azims, weights, **kwargs)
        Image.fromarray((texture.cpu().numpy().clip(0, 1) * 255).astype('uint8')).save(output / 'before_inpaint.png')
        Image.fromarray((mask.squeeze(-1).cpu().numpy() * 255).astype('uint8')).save(output / 'coverage.png')
        return texture, mask

    def inpaint(texture, mask):
        result = original_inpaint(texture, mask)
        Image.fromarray((result.cpu().numpy().clip(0, 1) * 255).astype('uint8')).save(output / 'after_inpaint.png')
        return result

    pipeline.bake_from_multiview = bake
    pipeline.texture_inpaint = inpaint
    mesh = trimesh.load(job / 'geometry' / 'hunyuan3d-2mv' / 'mesh.glb', force='mesh')
    images = [Image.open(job / 'references' / 'processed' / f'{view}.png').convert('RGBA')
              for view in ('front', 'left', 'back', 'right')]
    pipeline(mesh, image=images).export(output / 'official.glb')
    print('CAPTURE_COMPLETE', output, flush=True)


if __name__ == '__main__':
    main()
