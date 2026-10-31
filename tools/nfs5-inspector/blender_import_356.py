"""First-pass NFS5 356 Coupé assembly (experimental, deliberately not 993-specific).

Run:
  blender --background --python tools/nfs5-inspector/blender_import_356.py -- \
    ~/gitHub/project-356/batch ~/gitHub/project-356/scout/356_1-assembly.csv \
    --save-blend ~/gitHub/project-356/Porsche-356-first-pass.blend

All exported articles are imported and labelled. Only the plausible Coupé
body/roof/glass/core pieces are displayed. Wheel/door placement and original
textures remain unverified; no 993-specific adjustments are reused.
"""
import argparse
import csv
from pathlib import Path
import sys
import math

import bpy

# Article map observed in 356_1.crp. These are candidate visual groups, not
# proof of fit, orientation or original in-game visibility.
VISIBLE = {
    1, 2, 3, 6, 8, 9, 15, 16, 17, 21, 25, 35, 38,
}
GLASS = {18, 35, 36, 37, 38, 104, 110, 111}
ALTERNATIVE_ROOFS = {24, 30, 31}
MIRROR_CANDIDATES = {4, 103, 18, 104, 19, 105}
WHEEL_CANDIDATES = {22, 23, 106, 107}


def material(name, color, metallic=0, roughness=0.35, alpha=1):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, alpha)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
    return mat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", type=Path)
    ap.add_argument("metadata", type=Path)
    ap.add_argument("--save-blend", type=Path)
    ap.add_argument("--bonnet-y-offset", type=float, default=0.0,
                    help="Additional Blender +Y offset for article 3; requires --panel-transform-preview")
    ap.add_argument("--decklid-y-offset", type=float, default=0.0,
                    help="Additional Blender Y offset for article 6; requires --panel-transform-preview")
    ap.add_argument("--panel-transform-preview", action="store_true",
                    help="Apply candidate CRP translation and X=90-degree rotation to articles 3 and 6")
    ap.add_argument("--all-visible", action="store_true",
                    help="Diagnostic mode: show every imported mesh, including alternatives")
    options = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = ap.parse_args(options)
    if not args.panel_transform_preview and (args.bonnet_y_offset or args.decklid_y_offset):
        ap.error("Y offsets require --panel-transform-preview")
    batch = args.batch.expanduser().resolve()
    meta_path = args.metadata.expanduser().resolve()
    manifest = batch / "manifest.csv"
    if not manifest.is_file() or not meta_path.is_file():
        ap.error("Manifest or assembly metadata missing. Run --batch-mesh and --assembly-metadata first.")
    with meta_path.open(newline="") as handle:
        metadata = {int(r["article"]): r for r in csv.DictReader(handle)}

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    collection = bpy.data.collections.new("NFS5 356_1 — original CRP articles")
    bpy.context.scene.collection.children.link(collection)
    root = bpy.data.objects.new("Porsche_356_CRP_root", None)
    collection.objects.link(root)
    root["reconstruction_stage"] = "first-pass visual inventory; placement not verified"

    paint = material("356 • provisional ivory paint", (0.75, 0.72, 0.61), roughness=0.4)
    glass = material("356 • provisional blue-grey glass", (0.09, 0.17, 0.21),
                     roughness=0.14, alpha=0.43)
    rubber = material("356 • provisional dark detail", (0.025, 0.028, 0.03),
                      roughness=0.67)
    lamps = material("356 • provisional lamp face", (0.75, 0.77, 0.73),
                     roughness=0.18)

    imported = 0
    missing = []
    with manifest.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["status"] != "exported":
                continue
            index = int(row["article"])
            source = batch / row["file_or_reason"]
            if not source.is_file():
                missing.append(str(source))
                continue
            old = set(bpy.data.objects.keys())
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=str(source))
            else:
                bpy.ops.import_scene.obj(filepath=str(source))
            for number, obj in enumerate(o for o in bpy.data.objects if o.name not in old and o.type == "MESH"):
                obj.name = f"{index:03d}_{row['name']}" + (f"_{number}" if number else "")
                for existing in list(obj.users_collection):
                    existing.objects.unlink(obj)
                collection.objects.link(obj)
                obj.parent = root
                obj["crp_article"] = index
                obj["crp_name"] = row["name"]
                info = metadata.get(index, {})
                if info.get("has_transform") == "1":
                    obj["crp_original_translation_xyz"] = [
                        float(info[k]) for k in ("tx", "ty", "tz")
                    ]
                if args.panel_transform_preview and index in (3, 6):
                    if info.get("has_transform") == "1":
                        tx, ty, tz = (float(info[k]) for k in ("tx", "ty", "tz"))
                        y_offset = args.bonnet_y_offset if index == 3 else args.decklid_y_offset
                        obj.location = (tx, tz + y_offset, ty)
                        obj.rotation_euler = (math.pi / 2, 0.0, 0.0)
                        obj["placement_status"] = "EXPERIMENTAL CRP translation + X90 rotation"
                        print(f"356 PANEL PREVIEW: {index} {row['name']} "
                              f"translation_CR P=({tx:.4f},{ty:.4f},{tz:.4f}) "
                              f"Blender_location={tuple(round(v, 4) for v in obj.location)} "
                              f"rotation_X=90deg Y_offset={y_offset:+.4f}")
                    else:
                        print(f"356 PANEL PREVIEW: {index} has no metadata transform; unchanged")
                # Transform metadata is recorded, not blindly applied. Some
                # CRP mesh buffers already encode world positions and others
                # are local panel geometry; only a mesh-by-mesh review can tell.
                display = args.all_visible or index in VISIBLE
                obj.hide_set(not display)
                obj.hide_render = not display
                if index in GLASS:
                    obj.data.materials.clear()
                    obj.data.materials.append(glass)
                elif index in (8, 9, 21):
                    obj.data.materials.clear()
                    obj.data.materials.append(lamps)
                elif index in (1, 2, 15, 22, 23, 27, 28, 84, 85, 106, 107):
                    obj.data.materials.clear()
                    obj.data.materials.append(rubber)
                else:
                    obj.data.materials.clear()
                    obj.data.materials.append(paint)
                imported += 1

    scene = bpy.context.scene
    scene["nfs5_source"] = "356_1.crp"
    scene["nfs5_variant"] = "Coupé — provisional"
    scene["nfs5_caveats"] = (
        "Body, roof and glass article assignments inferred by name. "
        "Movable panels, wheels and duplicated parts are hidden pending placement. "
        "Materials are placeholders, not FSH originals."
    )
    for area in bpy.context.screen.areas if bpy.context.screen else ():
        if area.type == "VIEW_3D":
            area.spaces.active.shading.type = "MATERIAL"
    print(f"356 FIRST PASS: {imported} Blender meshes imported, {len(missing)} absent.")
    print(f"356 FIRST PASS: initially visible article IDs: {sorted(VISIBLE)}")
    if args.panel_transform_preview:
        print("356 PANEL PREVIEW: hypotheses only; compare against untransformed saved .blend")
    print(f"356 FIRST PASS: hidden roof alternatives: {sorted(ALTERNATIVE_ROOFS)}")
    print(f"356 FIRST PASS: hidden door candidates: {sorted(MIRROR_CANDIDATES)}")
    print(f"356 FIRST PASS: hidden wheels pending axle placement: {sorted(WHEEL_CANDIDATES)}")
    for path in missing:
        print(f"356 MISSING: {path}")
    if args.save_blend:
        output = args.save_blend.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(output))
        print(f"356 SAVED: {output}")


if __name__ == "__main__":
    main()
