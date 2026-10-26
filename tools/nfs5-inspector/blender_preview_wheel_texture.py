"""Preview locally extracted Porsche 993 wheel texture on UV-mapped OBJ in Blender.

Run:
blender --python tools/nfs5-inspector/blender_preview_wheel_texture.py -- \
  ~/gitHub/project-porsche/uv-test/wheel-front-uv.obj \
  ~/gitHub/project-porsche/textures-png/fs-2-15-whf.png
Does not modify the main assembly or original game assets.
"""
import bpy
import sys
from pathlib import Path
from mathutils import Vector


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) not in (2, 3):
        raise SystemExit("Usage: blender --python blender_preview_wheel_texture.py -- <wheel.obj> <texture.png> [preview.blend]")
    obj_path, texture_path = map(lambda x: Path(x).expanduser().resolve(), args[:2])
    if not obj_path.is_file() or not texture_path.is_file():
        raise FileNotFoundError("Wheel OBJ and PNG texture must exist locally")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.wm.obj_import(filepath=str(obj_path))
    wheels = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one wheel mesh, got {len(wheels)}")
    wheel = wheels[0]
    if not wheel.data.uv_layers:
        raise RuntimeError("Imported wheel has no UVs; check OBJ exporter")
    mat = bpy.data.materials.new("NFS5_original_wheel_whf_preview")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(texture_path), check_existing=True)
    texture.interpolation = "Linear"
    mat.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    if "Alpha" in bsdf.inputs:
        mat.node_tree.links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
    mat.diffuse_color = (0.8, 0.8, 0.8, 1)
    wheel.data.materials.clear()
    wheel.data.materials.append(mat)
    bpy.context.view_layer.objects.active = wheel
    wheel.select_set(True)
    # Wheel axle is X in native CRP coordinates. Preview face-on along X.
    bpy.ops.object.camera_add(location=(2.2, 0, 0))
    camera = bpy.context.object
    direction = Vector((0, 0, 0)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 1.05
    bpy.context.scene.camera = camera
    camera.hide_set(True)
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.shading.type = "MATERIAL"
            region = area.spaces.active.region_3d
            region.view_perspective = "ORTHO"
            region.view_rotation = camera.rotation_euler.to_quaternion()
            region.view_distance = 1.5
    print(f"WHEEL_TEXTURE_PREVIEW obj={obj_path.name} png={texture_path.name}")
    print(f"vertices={len(wheel.data.vertices)} polygons={len(wheel.data.polygons)} uv_loops={len(wheel.data.uv_layers.active.data)}")
    if len(args) == 3:
        target = Path(args[2]).expanduser().resolve()
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite {target}")
        bpy.ops.wm.save_as_mainfile(filepath=str(target))
        print(f"Saved preview blend file to {target}")


if __name__ == "__main__":
    main()
