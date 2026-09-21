from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _point_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def render_preview(source: Path, output: Path, size: int = 768, mode: str = "material", view: str = "front") -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [item for item in bpy.context.scene.objects if item.type == "MESH"]
    if not meshes:
        raise RuntimeError("GLB contains no mesh objects")

    # Diagnostic materials live only in this render scene. Never modify/export
    # the source asset. Albedo isolates texture detail from lighting and normals;
    # clay isolates geometry from the texture painted over it.
    if mode != "material":
        for material in bpy.data.materials:
            if not material.use_nodes:
                continue
            nodes = material.node_tree.nodes
            principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
            output_node = next((node for node in nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output), None)
            if principled is None or output_node is None:
                raise RuntimeError(f"Cannot inspect material {material.name}: no Principled/output node")
            if mode == "albedo":
                emission = nodes.new("ShaderNodeEmission")
                color = principled.inputs["Base Color"]
                emission.inputs["Color"].default_value = color.default_value
                if color.is_linked:
                    material.node_tree.links.new(color.links[0].from_socket, emission.inputs["Color"])
                material.node_tree.links.new(emission.outputs[0], output_node.inputs["Surface"])
            else:
                clay = nodes.new("ShaderNodeBsdfPrincipled")
                clay.inputs["Base Color"].default_value = (0.4, 0.4, 0.4, 1)
                clay.inputs["Roughness"].default_value = 0.85
                material.node_tree.links.new(clay.outputs[0], output_node.inputs["Surface"])

    corners = [item.matrix_world @ Vector(corner) for item in meshes for corner in item.bound_box]
    lower = Vector((min(item.x for item in corners), min(item.y for item in corners), min(item.z for item in corners)))
    upper = Vector((max(item.x for item in corners), max(item.y for item in corners), max(item.z for item in corners)))
    center = (lower + upper) / 2
    extent = max(upper.x - lower.x, upper.y - lower.y, upper.z - lower.z)

    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    # SPAR3D's exported coordinate system presents the reference-facing side
    # from +Y.  Keep the preview aligned with the source image by default.
    angle = {"front": 0, "side": math.pi / 2, "back": math.pi}[view]
    camera.location = center + Vector((math.sin(angle) * extent * 2.6, math.cos(angle) * extent * 2.6, extent * 0.12))
    camera_data.lens = 58
    camera_data.sensor_width = 36
    _point_camera(camera, center)
    bpy.context.scene.camera = camera

    world = bpy.context.scene.world or bpy.data.worlds.new("PreviewWorld")
    bpy.context.scene.world = world
    world.color = (0.035, 0.04, 0.05)
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.035, 0.04, 0.05, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    for name, location, energy, size_value in (
        ("Key", (extent * 1.5, extent * 2, extent * 2), 350, extent),
        ("Fill", (-extent * 1.5, extent, extent * 0.8), 180, extent * 0.8),
        ("Rim", (0, -extent * 1.8, extent * 1.5), 250, extent * 0.7),
    ):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size_value
        light = bpy.data.objects.new(name, light_data)
        bpy.context.collection.objects.link(light)
        light.location = location
        _point_camera(light, center)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in {
        item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    } else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.75
    if mode == "albedo":
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, default=768)
    parser.add_argument("--mode", choices=("material", "albedo", "clay"), default="material")
    parser.add_argument("--view", choices=("front", "side", "back"), default="front")
    # Blender keeps its own CLI arguments in sys.argv alongside the arguments
    # intended for this script.  Only parse the portion after the `--`
    # separator, otherwise argparse mistakes `-b`/`-P` for our options.
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(script_args)
    render_preview(args.source.resolve(), args.output.resolve(), args.size, args.mode, args.view)


if __name__ == "__main__":
    main()
