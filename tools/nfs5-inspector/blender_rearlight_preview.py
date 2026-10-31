"""Isolated NFS5 Porsche 993 rear-light UV and texture comparison.

blender --python tools/nfs5-inspector/blender_rearlight_preview.py -- UV_DIR PNG_DIR OUT.blend
Optional --scale-u N --scale-v N --offset-u N --offset-v N, common to both meshes.
No CRP material or UV orientation is assumed correct.
"""
import argparse
import bpy
import sys
from pathlib import Path


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("uv_dir", type=Path)
    parser.add_argument("png_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--auto-fit", action="store_true", help="fit each article UV island independently to 0..1")
    parser.add_argument("--flip-v", action="store_true", help="flip V in auto-fit mode")
    parser.add_argument("--scale-u", type=float, default=1.0)
    parser.add_argument("--scale-v", type=float, default=1.0)
    parser.add_argument("--offset-u", type=float, default=0.0)
    parser.add_argument("--offset-v", type=float, default=0.0)
    options = parser.parse_args(args)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for article, filename, row in (
        (17, "fs-0-24-lit2.png", 0),
        (18, "fs-0-25-lit3.png", 1),
    ):
        obj_path = options.uv_dir.expanduser() / f"article-{article}-uv.obj"
        image_path = options.png_dir.expanduser() / filename
        if not obj_path.is_file() or not image_path.is_file():
            raise FileNotFoundError(f"Missing OBJ or PNG: {obj_path}; {image_path}")
        before = set(bpy.data.objects.keys())
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(obj_path))
        else:
            bpy.ops.import_scene.obj(filepath=str(obj_path))
        imported = [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH"]
        if len(imported) != 1 or not imported[0].data.uv_layers:
            raise RuntimeError(f"article {article} needs exactly one UV mesh")
        obj = imported[0]
        obj.name = f"REAR_LIGHT_{article}_UNVERIFIED_{filename}"
        obj.location = (0, row * 1.5, 0)
        layer = obj.data.uv_layers.active
        uv = [(loop.uv.x, loop.uv.y) for loop in layer.data]
        print(f"REAR LIGHT UV article={article} raw U={min(x for x,y in uv):.6f}..{max(x for x,y in uv):.6f} "
              f"V={min(y for x,y in uv):.6f}..{max(y for x,y in uv):.6f}")
        if options.auto_fit:
            u_min, u_max = min(x for x,y in uv), max(x for x,y in uv)
            v_min, v_max = min(y for x,y in uv), max(y for x,y in uv)
            if u_max - u_min < 1e-8 or v_max - v_min < 1e-8:
                raise RuntimeError(f"Article {article} has degenerate UV bounds")
            su = 1.0 / (u_max - u_min)
            sv = (-1.0 if options.flip_v else 1.0) / (v_max - v_min)
            du = -u_min * su
            dv = (1.0 - v_min * sv) if options.flip_v else -v_min * sv
        else:
            su, sv = options.scale_u, options.scale_v
            du, dv = options.offset_u, options.offset_v
        print(f"REAR LIGHT TRANSFORM article={article} scale=({su:.6f},{sv:.6f}) "
              f"offset=({du:.6f},{dv:.6f}) auto_fit={options.auto_fit} flip_v={options.flip_v}")
        mat = bpy.data.materials.new(f"REAR_LIGHT_{article}_MATERIAL_TEST")
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(image_path.resolve()), check_existing=True)
        tex.extension = "CLIP"
        mapping = nodes.new("ShaderNodeVectorMath")
        mapping.operation = "MULTIPLY_ADD"
        mapping.inputs[1].default_value = (su, sv, 1.0)
        mapping.inputs[2].default_value = (du, dv, 0.0)
        uv_node = nodes.new("ShaderNodeUVMap")
        uv_node.uv_map = layer.name
        links.new(uv_node.outputs["UV"], mapping.inputs[0])
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        threshold = nodes.new("ShaderNodeMath")
        threshold.operation = "GREATER_THAN"
        threshold.inputs[1].default_value = 0.45
        links.new(tex.outputs["Alpha"], threshold.inputs[0])
        links.new(threshold.outputs[0], bsdf.inputs["Alpha"])
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "CLIP"
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        print(f"REAR LIGHT TEST article={article} polygons={len(obj.data.polygons)} image={filename} "
              f"scale=({su:.6f},{sv:.6f}) offset=({du:.6f},{dv:.6f})")
    output = options.output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output.resolve()))
    print(f"REAR LIGHT TEST saved {output}; no assembly changed")


if __name__ == "__main__":
    main()
