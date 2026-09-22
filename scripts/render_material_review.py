"""Render identical closeups and full views of an actual GLB with Blender."""
import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--albedo', action='store_true')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        for face in obj.data.polygons:
            face.use_smooth = True
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    if args.albedo:
        tex = next((n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE'), None)
        out = next(n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
        emission = mat.node_tree.nodes.new('ShaderNodeEmission')
        if tex:
            mat.node_tree.links.new(tex.outputs['Color'], emission.inputs['Color'])
        mat.node_tree.links.new(emission.outputs[0], out.inputs['Surface'])
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.world.color = (.25, .25, .25)
scene.view_settings.view_transform = 'Standard'
scene.render.image_settings.file_format = 'PNG'
for location, power, size in [((2,-4,4), 450, 5), ((-3,-1,2), 250, 4), ((0,3,3), 300, 3)]:
    bpy.ops.object.light_add(type='AREA', location=location)
    light = bpy.context.object
    light.data.energy = power
    light.data.shape = 'DISK'
    light.data.size = size
    light.rotation_euler = (Vector((0,0,0))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add()
cam = bpy.context.object
scene.camera = cam
cam.data.type = 'ORTHO'
# GLB Y-up is converted to Blender Z-up on import.
for name, target, position, scale in [
    ('front', (0,0,0), (0,-4,0), 2.3),
    ('back', (0,0,0), (0,4,0), 2.3),
    ('shoulder', (.35,0,.16), (2.2,-3,1.0), .65),
    ('face', (0,0,.63), (.35,-3,.70), .80),
]:
    cam.location = position
    cam.rotation_euler = (Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.ortho_scale = scale
    scene.render.filepath = str(output / f'{name}.png')
    bpy.ops.render.render(write_still=True)
