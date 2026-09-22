"""Remove isolated salt-and-pepper pixels from an embedded GLB atlas."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    import bpy
    import numpy as np

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    argv = sys.argv
    args = parser.parse_args(argv[argv.index("--") + 1 :] if "--" in argv else [])

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))

    for image in [item for item in bpy.data.images if item.size[0] and item.size[1]]:
        width, height = image.size[:]
        values = np.asarray(image.pixels[:], dtype=np.float32).reshape(height, width, 4)
        rgb = values[:, :, :3]
        radius = 1
        padded = np.pad(rgb, ((radius, radius), (radius, radius), (0, 0)), mode="edge")
        samples = np.stack(
            [padded[row : row + height, col : col + width] for row in range(3) for col in range(3)],
            axis=0,
        )
        median = np.median(samples, axis=0)
        mad = np.median(np.abs(samples - median[None, ...]), axis=0)
        outlier = (np.abs(rgb - median).mean(axis=2) > 0.18) & (mad.mean(axis=2) < 0.08)
        # Touch only isolated salt-and-pepper pixels; preserve the larger
        # painted regions that define the face, hair, seams and clothing.
        values[outlier, :3] = median[outlier]
        image.pixels[:] = values.reshape(-1).tolist()
        image.pack()

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=str(Path(args.output).resolve()),
        export_format="GLB",
        use_selection=True,
        export_materials="EXPORT",
        export_texcoords=True,
        export_normals=True,
    )


if __name__ == "__main__":
    main()
