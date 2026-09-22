from __future__ import annotations

import bpy
from mathutils import Vector


bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new("UtilityVest")
vertices = [(-0.38, -0.22, -0.18), (0.38, -0.22, -0.18), (0.38, 0.22, -0.18), (-0.38, 0.22, -0.18), (-0.38, -0.22, 0.52), (0.38, -0.22, 0.52), (0.38, 0.22, 0.52), (-0.38, 0.22, 0.52)]
faces = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7), (3, 2, 1, 0)]
mesh.from_pydata(vertices, [], faces)
mesh.update()
vest = bpy.data.objects.new("UtilityVest", mesh)
bpy.context.collection.objects.link(vest)
vest.location = Vector((0.0, 0.0, 0.28))
material = bpy.data.materials.new("UtilityVest_Material")
material.diffuse_color = (0.06, 0.18, 0.32, 1.0)
vest.data.materials.append(material)
bpy.context.view_layer.objects.active = vest
vest.select_set(True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath="D:/models/equipment-sources/utility-vest/UtilityVest.glb", export_format="GLB", export_materials="EXPORT", export_animations=False, export_skins=False)
