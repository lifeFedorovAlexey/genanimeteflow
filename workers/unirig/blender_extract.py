"""Extract UniRig's normalized raw mesh record through Blender's bpy runtime."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy

_USER_SITE = Path.home() / "AppData" / "Roaming" / "Python" / "Python311" / "site-packages"
if _USER_SITE.is_dir() and str(_USER_SITE) not in sys.path:
    sys.path.insert(0, str(_USER_SITE))


def main() -> None:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-faces", type=int, default=50000)
    args = parser.parse_args(script_args)

    unirig_root = Path(__import__("os").environ["UNIRIG_ROOT"])
    sys.path.insert(0, str(unirig_root))
    from src.data.extract import clean_bpy, load, process_armature, process_mesh, save_raw_data

    bpy.ops.wm.read_factory_settings(use_empty=True)
    clean_bpy()
    armature = load(str(args.input))
    arranged_bones = None
    if armature is not None:
        from src.data.extract import get_arranged_bones

        arranged_bones = get_arranged_bones(armature)
    vertices, faces, skin = process_mesh(arranged_bones)
    if arranged_bones is not None:
        joints, tails, parents, names, matrix_local = process_armature(armature, arranged_bones)
    else:
        joints = tails = parents = names = matrix_local = None
    save_raw_data(
        path=str(args.output),
        vertices=vertices,
        faces=faces - 1,
        skin=skin,
        joints=joints,
        tails=tails,
        parents=parents,
        names=names,
        matrix_local=matrix_local,
        target_count=args.target_faces,
    )
    print(f"UNIRIG_RAW_DATA_READY {args.output}")


if __name__ == "__main__":
    main()
