#!/usr/bin/env python3
"""Isolated texture/UV diagnostic for NFS5 Porsche 993 DoorWindow and Light1.

Usage (after --):
  blender --python tools/nfs5-inspector/blender_glass_light_preview.py -- \
    ~/gitHub/project-porsche/glass-light-uv \
    ~/gitHub/project-porsche/textures-png \
    ~/gitHub/project-porsche/glass-light-preview.blend

Optional: --glass FILE --headlight FILE --headlight-uv-scale 2.0
Images are diagnostic guesses, not verified CRP material bindings.
"""
import bpy
import sys
import argparse
from pathlib import Path


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) < 3:
        raise SystemExit("Usage: blender --python blender_glass_light_preview.py -- UV_DIR PNG_DIR OUTPUT_BLEND [--glass FILE] [--headlight FILE]")
    uv_dir, image_dir, destination = (Path(x).expanduser() for x in args[:3])
    parser = argparse.ArgumentParser()
    parser.add_argument("--headlight-uv-scale", type=float, default=1.0)
    parser.add_argument("--headlight-uv-offset-u", type=float, default=0.0)
    parser.add_argument("--headlight-uv-offset-v", type=float, default=0.0)
    options, _ = parser.parse_known_args(args[3:])
    if not (0.01 <= options.headlight_uv_scale <= 16.0):
        raise SystemExit("--headlight-uv-scale must be between 0.01 and 16")
    overrides = {}
    for opt, key in (("--glass", "glass"), ("--headlight", "headlight")):
        if opt in args:
            i = args.index(opt)
            if i + 1 >= len(args):
                raise SystemExit(f"{opt} requires an image path")
            overrides[key] = Path(args[i + 1]).expanduser()

    def choose(name, candidates):
        if name in overrides:
            path = overrides[name]
            if not path.is_file():
                raise FileNotFoundError(path)
            return path
        all_pngs = sorted(image_dir.glob("*.png"))
        matches = [p for p in all_pngs if any(token in p.stem.lower() for token in candidates)]
        if not matches:
            print(f"TEXTURE TEST: No candidate image found for {name} (tokens={candidates}); using checkerboard")
            return None
        print(f"TEXTURE TEST: {name} candidates: " + ", ".join(p.name for p in matches))
        print(f"TEXTURE TEST: testing first candidate {matches[0].name}; not an established material assignment")
        return matches[0]

    glass = choose("glass", ("glas",))
    head = choose("headlight", ("lit1",))
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    def material(label, source, transparent=False):
        mat = bpy.data.materials.new(label)
        mat.use_nodes = True
        tree = mat.node_tree
        bsdf = tree.nodes.get("Principled BSDF")
        bsdf.inputs["Roughness"].default_value = 0.25 if transparent else 0.42
        if transparent:
            bsdf.inputs["Metallic"].default_value = 0.0
        if source is not None:
            tex = tree.nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(str(source.resolve()), check_existing=True)
            tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            if transparent:
                # Preserve texture alpha when present; absent alpha stays opaque.
                tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
                if hasattr(mat, "surface_render_method"):
                    mat.surface_render_method = "DITHERED"
                elif hasattr(mat, "blend_method"):
                    mat.blend_method = "BLEND"
        else:
            checker = tree.nodes.new("ShaderNodeTexChecker")
            tree.links.new(checker.outputs["Color"], bsdf.inputs["Base Color"])
        return mat

    def import_part(article, label, image, location, transparent=False):
        path = uv_dir / f"article-{article}-uv.obj"
        if not path.is_file():
            raise FileNotFoundError(path)
        before = set(bpy.data.objects)
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(path))
        else:
            bpy.ops.import_scene.obj(filepath=str(path))
        imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
        if len(imported) != 1:
            raise RuntimeError(f"Expected exactly one mesh for article {article}; got {len(imported)}")
        obj = imported[0]
        obj.name = label
        obj.location = location
        if not obj.data.uv_layers:
            raise RuntimeError(f"No UV layer imported for article {article}")
        coords = [loop.uv for loop in obj.data.uv_layers.active.data]
        u = [xy.x for xy in coords]
        v = [xy.y for xy in coords]
        print(f"UV BOUNDS article={article}: U=[{min(u):.6f},{max(u):.6f}] V=[{min(v):.6f},{max(v):.6f}]")
        if article == 32:
            scale = options.headlight_uv_scale
            du, dv = options.headlight_uv_offset_u, options.headlight_uv_offset_v
            for loop in obj.data.uv_layers.active.data:
                loop.uv.x = loop.uv.x * scale + du
                loop.uv.y = loop.uv.y * scale + dv
            print(f"UV TRANSFORM article=32: scale={scale} offset=({du},{dv}) "
                  f"U=[{min(u)*scale+du:.6f},{max(u)*scale+du:.6f}] "
                  f"V=[{min(v)*scale+dv:.6f},{max(v)*scale+dv:.6f}]")
        obj.data.materials.clear()
        obj.data.materials.append(material(f"TEST_{label}", image, transparent))
        print(f"TEXTURE TEST: article={article} vertices={len(obj.data.vertices)} triangles={len(obj.data.polygons)} uv_layers={len(obj.data.uv_layers)} image={image}")
        return obj

    import_part(36, "DoorWindow_GLAS_UNVERIFIED", glass, (-1.5, 0, 0), True)
    import_part(32, "Light1_HEAD_UNVERIFIED", head, (1.5, 0, 0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(destination.resolve()))
    print(f"TEXTURE TEST: isolated blend saved: {destination}")
    print("TEXTURE TEST: inspect in Material Preview / UV Editing; no original assembly assets changed.")


if __name__ == "__main__":
    main()
