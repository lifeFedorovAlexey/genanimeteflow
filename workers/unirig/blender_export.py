"""Export UniRig prediction data through the installed Blender runtime."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
import numpy as np

# Blender's embedded Python may list the Windows user site without enabling it.
# The setup script installs SciPy there because it is also used by UniRig's
# official merge algorithm.
_USER_SITE = Path.home() / "AppData" / "Roaming" / "Python" / "Python311" / "site-packages"
if _USER_SITE.is_dir() and str(_USER_SITE) not in sys.path:
    sys.path.insert(0, str(_USER_SITE))
from scipy.spatial import cKDTree


def _load_prediction(path: Path) -> dict[str, object]:
    data = np.load(path, allow_pickle=True)
    return {name: data[name][()] for name in data}


def _import_mesh(path: Path) -> list[object]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [item for item in bpy.context.scene.objects if item.type == "MESH"]


def _mesh_from_prediction(data: dict[str, object]) -> object:
    vertices = np.asarray(data["vertices"], dtype=np.float32)
    faces = np.asarray(data["faces"], dtype=np.int32)
    mesh = bpy.data.meshes.new("character_mesh")
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new("character", mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _add_armature(data: dict[str, object]) -> object:
    joints = np.asarray(data["joints"], dtype=np.float32)
    tails = np.asarray(data.get("tails"), dtype=np.float32) if data.get("tails") is not None else None
    parents = list(data["parents"])
    names = [str(name) for name in data.get("names", [f"bone_{i}" for i in range(len(joints))])]
    arm_data = bpy.data.armatures.new("CharacterRig")
    armature = bpy.data.objects.new("CharacterRig", arm_data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = []
    for index, joint in enumerate(joints):
        bone = arm_data.edit_bones.new(names[index])
        bone.head = joint.tolist()
        if tails is not None and len(tails) > index:
            bone.tail = tails[index].tolist()
        else:
            bone.tail = (joint + np.array([0, 0.05, 0], dtype=np.float32)).tolist()
        if np.linalg.norm(np.asarray(bone.tail) - joint) < 1e-5:
            bone.tail = (joint + np.array([0, 0.05, 0], dtype=np.float32)).tolist()
        bones.append(bone)
    for index, parent in enumerate(parents):
        if parent is not None and int(parent) >= 0:
            bones[index].parent = bones[int(parent)]
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    return armature


def _world_vertices(meshes: list[object]) -> np.ndarray:
    points: list[np.ndarray] = []
    for mesh in meshes:
        matrix = np.asarray(mesh.matrix_world, dtype=np.float32)
        for vertex in mesh.data.vertices:
            point = matrix[:3, :3] @ np.asarray(vertex.co, dtype=np.float32) + matrix[:3, 3]
            points.append(point)
    if not points:
        raise ValueError("Source GLB has no mesh vertices")
    return np.stack(points)


def _align_prediction_to_mesh(
    meshes: list[object], skeleton: dict[str, object], skin: dict[str, object]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reproduce UniRig's normalized-space to source-mesh transfer.

    UniRig predicts skin weights on 32k normalized samples.  The official
    merge step maps those samples back to the original mesh with a KD-tree;
    using weights by raw vertex index would silently produce a wrong rig.
    """
    source_vertices = _world_vertices(meshes)
    sampled = np.asarray(skin["vertices"], dtype=np.float32)
    weights = np.asarray(skin["skin"], dtype=np.float32)
    joints = np.asarray(skin["joints"], dtype=np.float32)
    tails = np.asarray(skeleton["tails"], dtype=np.float32)
    if sampled.ndim != 2 or weights.ndim != 2 or sampled.shape[0] != weights.shape[0]:
        raise ValueError("UniRig skin prediction has incompatible vertices and weights")
    if weights.shape[1] != len(skeleton["names"]):
        raise ValueError("UniRig skin and skeleton bone counts do not match")

    min_values = source_vertices.min(axis=0)
    max_values = source_vertices.max(axis=0)
    center = (min_values + max_values) / 2.0
    scale = float(np.max(max_values - min_values) / 2.0)
    if scale <= 0:
        raise ValueError("Source mesh has zero size")
    sampled = sampled * scale + center
    bones = np.concatenate([joints, tails], axis=1) * scale
    bones[:, :3] += center
    bones[:, 3:] += center

    # The network's canonical axes are not guaranteed to match a GLB's axes.
    # Choose the transform with the smallest nearest-neighbour distance, as in
    # the official UniRig merge implementation.
    best_loss = float("inf")
    best_sampled = sampled
    best_bones = bones
    sample_for_alignment = sampled[:: max(1, len(sampled) // 16384)]
    for permutation in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)):
        permuted = sample_for_alignment[:, permutation]
        for signs in ((sx, sy, sz) for sx in (1.0, -1.0) for sy in (1.0, -1.0) for sz in (1.0, -1.0)):
            transformed = permuted * np.asarray(signs, dtype=np.float32)
            distances, _ = cKDTree(transformed).query(source_vertices)
            loss = float(distances.mean())
            if loss < best_loss:
                best_loss = loss
                best_sampled = sampled[:, permutation] * np.asarray(signs, dtype=np.float32)
                best_bones = bones[:, (list(permutation) + [p + 3 for p in permutation])]
                best_bones *= np.asarray(list(signs) + list(signs), dtype=np.float32)
    return best_sampled, best_bones, weights


def _apply_skin(meshes: list[object], armature: object, names: list[str], weights: np.ndarray, sampled: np.ndarray) -> None:
    tree = cKDTree(sampled)
    _, nearest = tree.query(_world_vertices(meshes))
    order = np.argsort(-weights, axis=1)
    top = order[:, :4]
    top_weights = np.take_along_axis(weights, top, axis=1)
    sums = top_weights.sum(axis=1, keepdims=True)
    top_weights = np.nan_to_num(top_weights / np.where(sums > 0, sums, 1.0))
    offset = 0
    for mesh in meshes:
        modifier = mesh.modifiers.new(name="CharacterRig", type="ARMATURE")
        modifier.object = armature
        groups = {name: mesh.vertex_groups.new(name=name) for name in names}
        matrix = np.asarray(mesh.matrix_world, dtype=np.float32)
        for vertex_index, vertex in enumerate(mesh.data.vertices):
            point = matrix[:3, :3] @ np.asarray(vertex.co, dtype=np.float32) + matrix[:3, 3]
            global_index = offset + vertex_index
            sample_index = int(nearest[global_index])
            for bone_index, value in zip(top[sample_index], top_weights[sample_index]):
                if value > 1e-6:
                    groups[names[int(bone_index)]].add([vertex_index], float(value), "REPLACE")
        mesh.parent = armature
        offset += len(mesh.data.vertices)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--mode", choices=("skeleton", "rigged"), required=True)
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(script_args)
    data = _load_prediction(args.prediction)
    meshes = _import_mesh(args.source) if args.mode == "rigged" and args.source else [_mesh_from_prediction(data)]
    if args.mode == "rigged":
        skin_path = args.prediction.with_name("predict_skin.npz")
        if not skin_path.is_file():
            raise FileNotFoundError(f"Expected UniRig skin prediction next to skeleton: {skin_path}")
        skin = _load_prediction(skin_path)
        sampled, bones, weights = _align_prediction_to_mesh(meshes, data, skin)
        rig_data = {"joints": bones[:, :3], "tails": bones[:, 3:], "parents": data["parents"], "names": data["names"]}
        armature = _add_armature(rig_data)
    else:
        armature = _add_armature(data)
    if args.mode == "rigged":
        _apply_skin(meshes, armature, [str(name) for name in data["names"]], weights, sampled)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    if args.output.suffix.lower() == ".fbx":
        bpy.ops.export_scene.fbx(filepath=str(args.output), check_existing=False, add_leaf_bones=False)
    else:
        bpy.ops.export_scene.gltf(filepath=str(args.output), export_format="GLB", export_skins=True, export_animations=True)


if __name__ == "__main__":
    main()
