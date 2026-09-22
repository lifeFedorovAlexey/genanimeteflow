"""Preserve the accepted shape, unwrap with Blender, export explicit corner UVs."""
import argparse
import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--faces', type=int, default=0)
parser.add_argument('--merge-small-charts', action='store_true')
parser.add_argument('--remove-floaters', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
obj = next(obj for obj in bpy.context.scene.objects if obj.type == 'MESH')
bpy.context.view_layer.objects.active = obj
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bm = bmesh.new()
bm.from_mesh(obj.data)
bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)
bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=1e-8)
if args.remove_floaters:
    unseen = set(bm.faces)
    components = []
    while unseen:
        stack = [unseen.pop()]
        component = []
        while stack:
            face = stack.pop()
            component.append(face)
            for edge in face.edges:
                for neighbor in edge.link_faces:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        stack.append(neighbor)
        components.append(component)
    threshold = max(map(len, components)) * .005
    small = [face for group in components if len(group) < threshold for face in group]
    print('PAINT_FLOATERS_REMOVED', len(small), flush=True)
    bmesh.ops.delete(bm, geom=small, context='FACES')
bm.to_mesh(obj.data)
bm.free()
if args.faces and len(obj.data.polygons) > args.faces:
    modifier = obj.modifiers.new('Paint topology', 'DECIMATE')
    modifier.ratio = args.faces / len(obj.data.polygons)
    modifier.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=modifier.name)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=.006)
bpy.ops.object.mode_set(mode='OBJECT')
if args.merge_small_charts:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    layer = bm.loops.layers.uv.active
    parent = list(range(len(bm.faces)))
    sizes = [1] * len(parent)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(a, b):
        a, b = find(a), find(b)
        if a == b:
            return
        if sizes[a] < sizes[b]:
            a, b = b, a
        parent[b] = a
        sizes[a] += sizes[b]

    adjacent = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        a, b = edge.link_faces
        adjacent.append((edge, a.index, b.index))
        loops = [next(loop for loop in f.loops if loop.edge == edge) for f in (a,b)]
        left = {loop.vert.index: loop[layer].uv.copy() for loop in (loops[0], loops[0].link_loop_next)}
        right = {loop.vert.index: loop[layer].uv.copy() for loop in (loops[1], loops[1].link_loop_next)}
        if all((left[i]-right[i]).length < 1e-6 for i in left):
            join(a.index, b.index)
    for _ in range(4):
        for edge, a, b in adjacent:
            if find(a) != find(b) and min(sizes[find(a)], sizes[find(b)]) < 32:
                join(a,b)
    for edge in bm.edges:
        edge.seam = len(edge.link_faces) != 2
    for edge, a, b in adjacent:
        edge.seam = find(a) != find(b)
    bm.to_mesh(obj.data)
    bm.free()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=.003)
    bpy.ops.uv.pack_islands(margin=.006)
    bpy.ops.object.mode_set(mode='OBJECT')
mesh = obj.data
mesh.calc_loop_triangles()
xyz = np.asarray([obj.matrix_world @ v.co for v in mesh.vertices], dtype=np.float32)
xyz = xyz[:, [0,2,1]] * np.array([1,1,-1], dtype=np.float32)
loops = np.asarray([t.loops for t in mesh.loop_triangles])
vertex_indices = np.asarray([loop.vertex_index for loop in mesh.loops])
uv = np.asarray([item.uv[:] for item in mesh.uv_layers.active.data], dtype=np.float32)
corners = np.concatenate([xyz[vertex_indices[loops]].reshape(-1,3), uv[loops].reshape(-1,2)], axis=1)
values, inverse = np.unique(corners, axis=0, return_inverse=True)
np.savez(args.output, vertices=values[:,:3], faces=inverse.reshape(-1,3), uv=values[:,3:])
print('PAINT_UV_COMPLETE', len(values), len(loops), flush=True)
