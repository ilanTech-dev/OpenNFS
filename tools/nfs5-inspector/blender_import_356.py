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
import bmesh

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
# Optional exterior trim: decals, wiper, antenna. Door handles already belong
# to --door-preview and lights 8/9/21 are already in the default view.
DETAIL_ARTICLES = {10, 11, 12, 26, 29, 73}
LIGHT_ARTICLES = {8: "Light1", 9: "Light3", 21: "Light2_"}
# Paired articles are provisional: original file lists two DoorOut articles
# and corresponding exterior window, glass and handle variants.
DOOR_GROUPS = {
    "A": {4, 18, 19, 36, 37, 43},
    "B": {103, 104, 105, 110, 111, 112},
}
DOOR_ARTICLES = DOOR_GROUPS["A"] | DOOR_GROUPS["B"]


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
    ap.add_argument("--exterior-detail-preview", action="store_true",
                    help="Show wiper, badges/decals and antenna candidates (transforms unverified)")
    ap.add_argument("--light-uv-directory", type=Path,
                    help="Optional UV OBJ directory for articles 8/9/21 from --article-uv-mesh")
    ap.add_argument("--headlight-uv-scale", type=float, default=5.7)
    ap.add_argument("--aux-light-uv-scale", type=float, default=1.0)
    ap.add_argument("--rear-light-uv-scale", type=float, default=1.0)
    ap.add_argument("--headlight-uv-offset-u", type=float, default=0.0)
    ap.add_argument("--headlight-uv-offset-v", type=float, default=0.0)
    ap.add_argument("--aux-light-uv-offset-u", type=float, default=0.0)
    ap.add_argument("--aux-light-uv-offset-v", type=float, default=0.0)
    ap.add_argument("--rear-light-uv-offset-u", type=float, default=0.0)
    ap.add_argument("--rear-light-uv-offset-v", type=float, default=0.0)
    ap.add_argument("--light-texture-directory", type=Path,
                    help="Optional extracted PNG directory for experimental original 356 light materials")
    ap.add_argument("--bonnet-y-offset", type=float, default=1.21,
                    help="Additional Blender +Y offset for article 3; requires --panel-transform-preview")
    ap.add_argument("--decklid-y-offset", type=float, default=-2.23,
                    help="Additional Blender Y offset for article 6; requires --panel-transform-preview")
    ap.add_argument("--panel-transform-preview", action="store_true",
                    help="Apply candidate CRP translation and X=90-degree rotation to articles 3 and 6")
    ap.add_argument("--door-preview", action="store_true",
                    help="Display both candidate door/window sets with their CRP transforms")
    ap.add_argument("--door-a-y-offset", type=float, default=1.47,
                    help="Additional Blender Y translation for door group A")
    ap.add_argument("--door-b-y-offset", type=float, default=1.47,
                    help="Additional Blender Y translation for door group B")
    ap.add_argument("--door-a-x-offset", type=float, default=0.0,
                    help="Additional Blender X translation for door group A")
    ap.add_argument("--door-b-x-offset", type=float, default=0.0,
                    help="Additional Blender X translation for door group B")
    ap.add_argument("--wheel-uv-directory", type=Path,
                    help="Directory containing 22_WheelFront.obj, 23_WheelRear.obj, 106_WheelFront.obj, 107_WheelRear.obj exported with --wheel-uv-mesh")
    ap.add_argument("--wheel-backing-texture", type=Path,
                    help="Candidate RGBA PNG for original square backing triangles 112/113")
    ap.add_argument("--wheel-backing-uv-scale", type=float, default=1.0)
    ap.add_argument("--wheel-backing-alpha-threshold", type=float, default=0.5)
    ap.add_argument("--wheel-remove-backing", action="store_true",
                    help="Remove only validated backing triangles 112/113 from 356 wheel Blender meshes")
    ap.add_argument("--wheel-backing-hide", action="store_true",
                    help="Diagnostic: hide only the two confirmed square backing triangles (112,113), preserving tyre")
    ap.add_argument("--wheel-radial-audit", action="store_true",
                    help="Mark individual wheel triangles outside the inferred Y/Z circular profile")
    ap.add_argument("--wheel-radial-limit", type=float, default=0.325,
                    help="Radial distance threshold in wheel-local Y/Z for --wheel-radial-audit")
    ap.add_argument("--wheel-tire-geometry-audit", action="store_true",
                    help="Color and log wheel UV regions with geometric local bounding boxes; no faces hidden")
    ap.add_argument("--wheel-strip-transparent", action="store_true",
                    help="Experimental: make the non-circular wheel UV region fully transparent")
    ap.add_argument("--wheel-tire-texture", type=Path,
                    help="Second original FSH PNG for rectangular tyre-region faces")
    ap.add_argument("--wheel-tire-uv-scale", type=float, default=1.0,
                    help="Separate shader UV scale for tyre image")
    ap.add_argument("--wheel-two-materials", action="store_true",
                    help="Apply wheel-face artwork to circular faces and tyre artwork to strip faces")
    ap.add_argument("--wheel-face-only", action="store_true",
                    help="Apply wheel image only to candidate circular UV faces; dark material elsewhere")
    ap.add_argument("--wheel-uv-regions", action="store_true",
                    help="Debug: colour wheel face UV island cyan and upper rectangular island magenta")
    ap.add_argument("--wheel-uv-region-v", type=float, default=0.50,
                    help="Original UV V threshold separating candidate wheel regions")
    ap.add_argument("--wheel-uv-scale", type=float, default=1.0,
                    help="Experimental UV multiplier for wheel texture (try 2.0); no OBJ coordinates changed")
    ap.add_argument("--wheel-texture", type=Path,
                    help="Optional local FSH-extracted wheel PNG; identity and UV transform require visual verification")
    ap.add_argument("--wheel-swap-axle-y", action="store_true",
                    help="Exchange longitudinal CRP translations for paired wheel articles 22/23 and 106/107; requires --wheel-preview")
    ap.add_argument("--wheel-preview", action="store_true",
                    help="Show original 356 wheel articles at CRP metadata translations; no mirroring")
    ap.add_argument("--front-wheel-x-offset", type=float, default=0.0)
    ap.add_argument("--front-wheel-y-offset", type=float, default=0.16)
    ap.add_argument("--front-wheel-z-offset", type=float, default=0.0)
    ap.add_argument("--rear-wheel-x-offset", type=float, default=0.0)
    ap.add_argument("--rear-wheel-y-offset", type=float, default=0.15)
    ap.add_argument("--rear-wheel-z-offset", type=float, default=0.0)
    ap.add_argument("--all-visible", action="store_true",
                    help="Diagnostic mode: show every imported mesh, including alternatives")
    options = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = ap.parse_args(options)
    if any(v <= 0 for v in (args.headlight_uv_scale, args.aux_light_uv_scale, args.rear_light_uv_scale)):
        ap.error("Light UV scales must be positive")
    if args.light_texture_directory and not args.light_uv_directory:
        ap.error("--light-texture-directory requires --light-uv-directory")
    if not args.panel_transform_preview and (args.bonnet_y_offset != 1.21 or args.decklid_y_offset != -2.23):
        ap.error("Y offsets require --panel-transform-preview")
    if not args.door_preview and any((args.door_a_y_offset, args.door_b_y_offset,
                                      args.door_a_x_offset, args.door_b_x_offset)):
        ap.error("Door offsets require --door-preview")
    if (args.wheel_uv_directory or args.wheel_texture) and not args.wheel_preview:
        ap.error("Wheel UV/textures require --wheel-preview")
    if args.wheel_two_materials:
        if not (args.wheel_tire_texture and args.wheel_texture and args.wheel_uv_directory and args.wheel_preview):
            ap.error("--wheel-two-materials requires --wheel-tire-texture, --wheel-texture, --wheel-uv-directory and --wheel-preview")
        if args.wheel_face_only or args.wheel_uv_regions or args.wheel_tire_geometry_audit or args.wheel_strip_transparent:
            ap.error("--wheel-two-materials cannot combine with other wheel region tests")
    if args.wheel_tire_uv_scale <= 0:
        ap.error("--wheel-tire-uv-scale must be positive")
    if args.wheel_face_only and (not args.wheel_texture or not args.wheel_uv_directory or not args.wheel_preview):
        ap.error("--wheel-face-only requires --wheel-texture, --wheel-uv-directory and --wheel-preview")
    if args.wheel_backing_texture:
        if not (args.wheel_preview and args.wheel_uv_directory):
            ap.error("--wheel-backing-texture requires --wheel-preview and --wheel-uv-directory")
        if args.wheel_remove_backing or args.wheel_backing_hide or args.wheel_radial_audit:
            ap.error("--wheel-backing-texture conflicts with other backing diagnostics")
    if args.wheel_backing_uv_scale <= 0 or not 0 <= args.wheel_backing_alpha_threshold <= 1:
        ap.error("Invalid backing UV scale or alpha threshold")
    if args.wheel_remove_backing and (not args.wheel_preview or not args.wheel_uv_directory):
        ap.error("--wheel-remove-backing requires --wheel-preview and --wheel-uv-directory")
    if args.wheel_remove_backing and (args.wheel_backing_hide or args.wheel_radial_audit or args.wheel_tire_geometry_audit):
        ap.error("--wheel-remove-backing conflicts with backing transparency and geometry audits")
    if args.wheel_backing_hide and (not args.wheel_preview or not args.wheel_uv_directory):
        ap.error("--wheel-backing-hide requires --wheel-preview and --wheel-uv-directory")
    if args.wheel_backing_hide and (args.wheel_radial_audit or args.wheel_uv_regions or args.wheel_tire_geometry_audit or args.wheel_strip_transparent):
        ap.error("--wheel-backing-hide conflicts with diagnostic coloring or whole-strip transparency")
    if args.wheel_radial_audit and (not args.wheel_preview or not args.wheel_uv_directory):
        ap.error("--wheel-radial-audit requires --wheel-preview and --wheel-uv-directory")
    if args.wheel_radial_limit <= 0:
        ap.error("--wheel-radial-limit must be positive")
    if args.wheel_radial_audit and (args.wheel_tire_geometry_audit or args.wheel_uv_regions or args.wheel_face_only or args.wheel_two_materials or args.wheel_strip_transparent):
        ap.error("--wheel-radial-audit is exclusive with other wheel material diagnostics")
    if args.wheel_tire_geometry_audit and (not args.wheel_preview or not args.wheel_uv_directory):
        ap.error("--wheel-tire-geometry-audit requires --wheel-preview and --wheel-uv-directory")
    if args.wheel_tire_geometry_audit and (args.wheel_face_only or args.wheel_uv_regions or args.wheel_strip_transparent):
        ap.error("--wheel-tire-geometry-audit cannot be combined with other wheel region modes")
    if args.wheel_strip_transparent and not args.wheel_face_only:
        ap.error("--wheel-strip-transparent requires --wheel-face-only")
    if args.wheel_face_only and args.wheel_uv_regions:
        ap.error("Choose one of --wheel-face-only and --wheel-uv-regions")
    if args.wheel_uv_regions and (not args.wheel_preview or not args.wheel_uv_directory):
        ap.error("--wheel-uv-regions requires --wheel-preview and --wheel-uv-directory")
    if not 0 < args.wheel_uv_region_v < 1:
        ap.error("--wheel-uv-region-v must be between 0 and 1")
    if args.wheel_uv_scale <= 0:
        ap.error("--wheel-uv-scale must be positive")
    if args.wheel_uv_scale != 1.0 and not args.wheel_texture:
        ap.error("--wheel-uv-scale requires --wheel-texture")
    if args.wheel_texture and not args.wheel_uv_directory:
        ap.error("--wheel-texture requires --wheel-uv-directory")
    if args.wheel_swap_axle_y and not args.wheel_preview:
        ap.error("--wheel-swap-axle-y requires --wheel-preview")
    if not args.wheel_preview and any((
        args.front_wheel_x_offset, args.front_wheel_y_offset, args.front_wheel_z_offset,
        args.rear_wheel_x_offset, args.rear_wheel_y_offset, args.rear_wheel_z_offset
    )):
        ap.error("Wheel offsets require --wheel-preview")
    batch = args.batch.expanduser().resolve()
    meta_path = args.metadata.expanduser().resolve()
    manifest = batch / "manifest.csv"
    if not manifest.is_file() or not meta_path.is_file():
        ap.error("Manifest or assembly metadata missing. Run --batch-mesh and --assembly-metadata first.")
    with meta_path.open(newline="") as handle:
        metadata = {int(r["article"]): r for r in csv.DictReader(handle)}

    # Keep each wheel's own X/Z placement, but optionally borrow the longitudinal
    # translation of the opposite-axle partner (matching article pair, not mesh).
    opposite_wheel = {22: 23, 23: 22, 106: 107, 107: 106}

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

    light_uv_dir = args.light_uv_directory.expanduser().resolve() if args.light_uv_directory else None
    light_png_dir = args.light_texture_directory.expanduser().resolve() if args.light_texture_directory else None
    light_uv_files = {article: f"{article}_{name}.obj" for article, name in LIGHT_ARTICLES.items()}
    if light_uv_dir:
        missing_light_uv = [str(light_uv_dir / name) for name in light_uv_files.values()
                            if not (light_uv_dir / name).is_file()]
        if missing_light_uv:
            ap.error("Missing light UV OBJ files: " + ", ".join(missing_light_uv))
    # Candidate assignments based on extracted filenames. Actual material links
    # and additional original shader UV transforms are not yet established.
    light_png_candidates = {8: "fs-0-08-lit1.png",
                            9: "fs-0-19-lit3.png", 21: "fs-0-18-lit2.png"}
    light_materials = {}
    if light_png_dir:
        for article, filename in light_png_candidates.items():
            image_path = light_png_dir / filename
            if not image_path.is_file():
                ap.error(f"Missing candidate light texture: {image_path}")
            image = bpy.data.images.load(str(image_path), check_existing=True)
            mat = material(f"356 — experimental {LIGHT_ARTICLES[article]} {filename}",
                           (1, 1, 1), roughness=0.22)
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
            tex.image = image
            tex.extension = "CLIP"
            controls = {
                8: (args.headlight_uv_scale, args.headlight_uv_offset_u, args.headlight_uv_offset_v),
                9: (args.aux_light_uv_scale, args.aux_light_uv_offset_u, args.aux_light_uv_offset_v),
                21: (args.rear_light_uv_scale, args.rear_light_uv_offset_u, args.rear_light_uv_offset_v),
            }
            uv_scale, offset_u, offset_v = controls[article]
            uv = mat.node_tree.nodes.new("ShaderNodeTexCoord")
            mapping = mat.node_tree.nodes.new("ShaderNodeVectorMath")
            mapping.operation = "SCALE"
            mapping.inputs[3].default_value = uv_scale
            offset = mat.node_tree.nodes.new("ShaderNodeVectorMath")
            offset.operation = "ADD"
            offset.inputs[1].default_value = (offset_u, offset_v, 0.0)
            mat.node_tree.links.new(uv.outputs["UV"], mapping.inputs[0])
            mat.node_tree.links.new(mapping.outputs["Vector"], offset.inputs[0])
            mat.node_tree.links.new(offset.outputs["Vector"], tex.inputs["Vector"])
            mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            mat.node_tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            if hasattr(mat, "surface_render_method"):
                mat.surface_render_method = "DITHERED"
            elif hasattr(mat, "blend_method"):
                mat.blend_method = "CLIP"
            light_materials[article] = mat

    wheel_uv_dir = args.wheel_uv_directory.expanduser().resolve() if args.wheel_uv_directory else None
    wheel_texture = args.wheel_texture.expanduser().resolve() if args.wheel_texture else None
    wheel_uv_files = {
        22: "22_WheelFront.obj", 23: "23_WheelRear.obj",
        106: "106_WheelFront.obj", 107: "107_WheelRear.obj",
    }
    if wheel_uv_dir:
        missing_uv = [str(wheel_uv_dir / file) for file in wheel_uv_files.values()
                      if not (wheel_uv_dir / file).is_file()]
        if missing_uv:
            ap.error("Missing wheel UV OBJ files: " + ", ".join(missing_uv))
    region_mats = (
        material("356 WHEEL UV REGION: circular candidate — cyan", (0.015, 0.7, 0.9), roughness=0.8),
        material("356 WHEEL UV REGION: upper strip — magenta", (0.95, 0.04, 0.5), roughness=0.8),
        material("356 WHEEL UV REGION: crossing threshold — yellow", (0.95, 0.8, 0.02), roughness=0.8),
    ) if (args.wheel_uv_regions or args.wheel_tire_geometry_audit) else None
    wheel_strip_invisible = None
    if args.wheel_strip_transparent:
        wheel_strip_invisible = material(
            "356 WHEEL DIAGNOSTIC — fully transparent UV strip", (0, 0, 0),
            roughness=1, alpha=0.0
        )
        wheel_strip_invisible.use_nodes = True
        transparent_nodes = wheel_strip_invisible.node_tree.nodes
        transparent_nodes.clear()
        output_node = transparent_nodes.new("ShaderNodeOutputMaterial")
        transparent_node = transparent_nodes.new("ShaderNodeBsdfTransparent")
        wheel_strip_invisible.node_tree.links.new(
            transparent_node.outputs["BSDF"], output_node.inputs["Surface"]
        )
    radial_mats = (
        material("356 radial audit — within circle (blue)", (0.02, 0.25, 0.72), roughness=0.85),
        material("356 radial audit — crosses circle (orange)", (1.0, 0.38, 0.02), roughness=0.85),
        material("356 radial audit — entirely outside circle (red)", (0.95, 0.02, 0.08), roughness=0.85),
    ) if args.wheel_radial_audit else None
    backing_transparent = None
    if args.wheel_backing_hide:
        backing_transparent = bpy.data.materials.new("356 — backing quad hidden (diagnostic)")
        backing_transparent.use_nodes = True
        backing_nodes = backing_transparent.node_tree.nodes
        backing_nodes.clear()
        out = backing_nodes.new("ShaderNodeOutputMaterial")
        transparent = backing_nodes.new("ShaderNodeBsdfTransparent")
        backing_transparent.node_tree.links.new(transparent.outputs["BSDF"], out.inputs["Surface"])
    backing_mat = None
    if args.wheel_backing_texture:
        backing_path = args.wheel_backing_texture.expanduser().resolve()
        if not backing_path.is_file():
            ap.error(f"Backing image missing: {backing_path}")
        backing_image = bpy.data.images.load(str(backing_path), check_existing=True)
        backing_mat = bpy.data.materials.new("356 — candidate alpha-clipped wheel backing")
        backing_mat.use_nodes = True
        nodes = backing_mat.node_tree.nodes
        nodes.clear()
        output_node = nodes.new("ShaderNodeOutputMaterial")
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = backing_image
        tex.extension = "CLIP"
        uv = nodes.new("ShaderNodeTexCoord")
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        scale.inputs[3].default_value = args.wheel_backing_uv_scale
        threshold = nodes.new("ShaderNodeMath")
        threshold.operation = "GREATER_THAN"
        threshold.inputs[1].default_value = args.wheel_backing_alpha_threshold
        links = backing_mat.node_tree.links
        links.new(uv.outputs["UV"], scale.inputs[0])
        links.new(scale.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Color"], shader.inputs["Base Color"])
        links.new(tex.outputs["Alpha"], threshold.inputs[0])
        links.new(threshold.outputs["Value"], shader.inputs["Alpha"])
        links.new(shader.outputs["BSDF"], output_node.inputs["Surface"])
        if hasattr(backing_mat, "surface_render_method"):
            backing_mat.surface_render_method = "DITHERED"
        elif hasattr(backing_mat, "blend_method"):
            backing_mat.blend_method = "CLIP"
            backing_mat.alpha_threshold = args.wheel_backing_alpha_threshold
    wheel_tire_mat = None
    if args.wheel_two_materials:
        tire_path = args.wheel_tire_texture.expanduser().resolve()
        if not tire_path.is_file():
            ap.error(f"Missing tyre texture: {tire_path}")
        tire_image = bpy.data.images.load(str(tire_path), check_existing=True)
        wheel_tire_mat = material("356 • experimental FSH tyre strip", (1, 1, 1))
        tire_nodes = wheel_tire_mat.node_tree.nodes
        tire_shader = tire_nodes.get("Principled BSDF")
        tire_node = tire_nodes.new("ShaderNodeTexImage")
        tire_node.image = tire_image
        tire_node.extension = "REPEAT"
        tire_uv = tire_nodes.new("ShaderNodeTexCoord")
        tire_scale = tire_nodes.new("ShaderNodeVectorMath")
        tire_scale.operation = "SCALE"
        tire_scale.inputs[3].default_value = args.wheel_tire_uv_scale
        wheel_tire_mat.node_tree.links.new(tire_uv.outputs["UV"], tire_scale.inputs[0])
        wheel_tire_mat.node_tree.links.new(tire_scale.outputs["Vector"], tire_node.inputs["Vector"])
        wheel_tire_mat.node_tree.links.new(tire_node.outputs["Color"], tire_shader.inputs["Base Color"])
        wheel_tire_mat.node_tree.links.new(tire_node.outputs["Alpha"], tire_shader.inputs["Alpha"])
        if hasattr(wheel_tire_mat, "surface_render_method"):
            wheel_tire_mat.surface_render_method = "DITHERED"
        elif hasattr(wheel_tire_mat, "blend_method"):
            wheel_tire_mat.blend_method = "CLIP"

    wheel_mat = None
    if wheel_texture:
        if not wheel_texture.is_file():
            ap.error(f"Missing wheel image: {wheel_texture}")
        image = bpy.data.images.load(str(wheel_texture), check_existing=True)
        wheel_mat = material("356 • experimental original wheel atlas (unverified)", (1, 1, 1))
        nodes = wheel_mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = "REPEAT"
        uv_map = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeVectorMath")
        mapping.operation = "SCALE"
        mapping.inputs[3].default_value = args.wheel_uv_scale
        wheel_mat.node_tree.links.new(uv_map.outputs["UV"], mapping.inputs[0])
        wheel_mat.node_tree.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        wheel_mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        wheel_mat.node_tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        if hasattr(wheel_mat, "surface_render_method"):
            wheel_mat.surface_render_method = "DITHERED"
        elif hasattr(wheel_mat, "blend_method"):
            wheel_mat.blend_method = "CLIP"

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
            if light_uv_dir is not None and index in light_uv_files:
                source = light_uv_dir / light_uv_files[index]
            if wheel_uv_dir is not None and index in wheel_uv_files:
                source = wheel_uv_dir / wheel_uv_files[index]
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
                if args.door_preview and index in DOOR_ARTICLES:
                    group = "A" if index in DOOR_GROUPS["A"] else "B"
                    delta_x = args.door_a_x_offset if group == "A" else args.door_b_x_offset
                    delta_y = args.door_a_y_offset if group == "A" else args.door_b_y_offset
                    if info.get("has_transform") == "1":
                        tx, ty, tz = (float(info[k]) for k in ("tx", "ty", "tz"))
                        obj.location = (tx + delta_x, tz + delta_y, ty)
                        obj.rotation_euler = (math.pi / 2, 0, 0)
                        obj["placement_status"] = "EXPERIMENTAL door CRP transform; compare mesh fit"
                        print(f"356 DOOR: group={group} article={index} "
                              f"CRP=({tx:.4f}, {ty:.4f}, {tz:.4f}) "
                              f"Blender={tuple(round(v, 4) for v in obj.location)} "
                              f"offset_XY=({delta_x:+.3f}, {delta_y:+.3f})")
                    else:
                        # No reliable world placement inferred from article name.
                        obj.location.x += delta_x
                        obj.location.y += delta_y
                        print(f"356 DOOR: group={group} article={index} has no CRP transform; "
                              "only user offsets applied")
                if args.wheel_preview and index in WHEEL_CANDIDATES:
                    axle = "front" if index in (22, 106) else "rear"
                    delta = (
                        (args.front_wheel_x_offset, args.front_wheel_y_offset,
                         args.front_wheel_z_offset) if axle == "front" else
                        (args.rear_wheel_x_offset, args.rear_wheel_y_offset,
                         args.rear_wheel_z_offset)
                    )
                    if info.get("has_transform") == "1":
                        tx, ty, tz = (float(info[k]) for k in ("tx", "ty", "tz"))
                        source_tz = tz
                        if args.wheel_swap_axle_y:
                            partner = metadata.get(opposite_wheel[index], {})
                            if partner.get("has_transform") == "1":
                                source_tz = float(partner["tz"])
                            else:
                                print(f"356 WHEEL WARNING: partner {opposite_wheel[index]} lacks transform; "
                                      f"article {index} retains its own Y")
                        obj.location = (tx + delta[0], source_tz + delta[1], ty + delta[2])
                        obj["placement_status"] = "EXPERIMENTAL CRP wheel translation; orientation unverified"
                    else:
                        obj.location = delta
                        obj["placement_status"] = "No CRP transform; offset only"
                    print(f"356 WHEEL: article={index} axle={axle} "
                          f"has_transform={info.get('has_transform', '?')} "
                          f"position={tuple(round(v, 4) for v in obj.location)} "
                          f"mesh_bbox_local={[(round(min(v[i] for v in obj.bound_box), 3), round(max(v[i] for v in obj.bound_box), 3)) for i in range(3)]}")
                # Transform metadata is recorded, not blindly applied. Some
                # CRP mesh buffers already encode world positions and others
                # are local panel geometry; only a mesh-by-mesh review can tell.
                display = (args.all_visible or index in VISIBLE or
                           (args.exterior_detail_preview and index in DETAIL_ARTICLES) or
                           (args.door_preview and index in DOOR_ARTICLES) or
                           (args.wheel_preview and index in WHEEL_CANDIDATES))
                obj.hide_set(not display)
                obj.hide_render = not display
                if index in WHEEL_CANDIDATES and args.wheel_radial_audit:
                    mesh = obj.data
                    mesh.materials.clear()
                    for mat in radial_mats:
                        mesh.materials.append(mat)
                    counts = [0, 0, 0]
                    for face in mesh.polygons:
                        radii = [math.hypot(mesh.vertices[k].co.y, mesh.vertices[k].co.z)
                                 for k in face.vertices]
                        label = (0 if max(radii) <= args.wheel_radial_limit else
                                 2 if min(radii) > args.wheel_radial_limit else 1)
                        face.material_index = label
                        counts[label] += 1
                        if label:
                            xyz = [tuple(round(mesh.vertices[k].co[a], 5) for a in range(3))
                                   for k in face.vertices]
                            print(f"356 RADIAL FACE: article={index} polygon={face.index} "
                                  f"region={label} radii={[round(v,5) for v in radii]} "
                                  f"xyz={xyz}")
                    print(f"356 RADIAL SUMMARY: article={index} "
                          f"radius_limit={args.wheel_radial_limit:.5f} "
                          f"inside={counts[0]} crossing={counts[1]} outside={counts[2]}")
                elif index in WHEEL_CANDIDATES and (args.wheel_uv_regions or args.wheel_face_only or args.wheel_tire_geometry_audit or args.wheel_two_materials):
                    mesh = obj.data
                    if not mesh.uv_layers:
                        raise RuntimeError(f"Wheel article {index}: no UV layer in {source}")
                    mesh.materials.clear()
                    if args.wheel_two_materials:
                        mesh.materials.append(wheel_mat)
                        mesh.materials.append(wheel_tire_mat)
                        mesh.materials.append(wheel_tire_mat)
                    elif args.wheel_face_only:
                        mesh.materials.append(wheel_mat)
                        mesh.materials.append(wheel_strip_invisible if args.wheel_strip_transparent else rubber)
                        mesh.materials.append(wheel_strip_invisible if args.wheel_strip_transparent else rubber)
                    else:
                        for region in region_mats:
                            mesh.materials.append(region)
                    uv_data = mesh.uv_layers.active.data
                    totals = [0, 0, 0]
                    for polygon in mesh.polygons:
                        vcoords = [uv_data[loop_index].uv.y
                                   for loop_index in polygon.loop_indices]
                        if max(vcoords) <= args.wheel_uv_region_v:
                            group = 0
                        elif min(vcoords) >= args.wheel_uv_region_v:
                            group = 1
                        else:
                            group = 2
                        polygon.material_index = group
                        totals[group] += 1
                    if args.wheel_tire_geometry_audit:
                        for group in range(3):
                            vertices = {vertex for polygon in mesh.polygons
                                        if polygon.material_index == group
                                        for vertex in polygon.vertices}
                            if not vertices:
                                continue
                            extrema = [(round(min(mesh.vertices[k].co[axis] for k in vertices), 5),
                                        round(max(mesh.vertices[k].co[axis] for k in vertices), 5))
                                       for axis in range(3)]
                            print(f"356 WHEEL GEOMETRY: article={index} region={group} "
                                  f"faces={totals[group]} verts={len(vertices)} "
                                  f"local_XYZ_ranges={extrema}")
                    print(f"356 WHEEL UV {'FACE-ONLY' if args.wheel_face_only else 'REGIONS'}: article={index} total={len(mesh.polygons)} "
                          f"circular={totals[0]} strip={totals[1]} crossing={totals[2]} "
                          f"threshold_V={args.wheel_uv_region_v:.3f}")
                elif index in WHEEL_CANDIDATES and wheel_mat:
                    obj.data.materials.clear()
                    obj.data.materials.append(wheel_mat)
                    if not obj.data.uv_layers:
                        raise RuntimeError(f"Wheel article {index}: UV layer absent in {source}")
                elif index in GLASS:
                    obj.data.materials.clear()
                    obj.data.materials.append(glass)
                elif index in LIGHT_ARTICLES:
                    obj.data.materials.clear()
                    obj.data.materials.append(light_materials.get(index, lamps))
                    if index in light_materials and not obj.data.uv_layers:
                        raise RuntimeError(f"356 light article {index}: imported OBJ lacks UVs: {source}")
                elif index in (1, 2, 15, 22, 23, 27, 28, 84, 85, 106, 107):
                    obj.data.materials.clear()
                    obj.data.materials.append(rubber)
                else:
                    obj.data.materials.clear()
                    obj.data.materials.append(paint)
                if backing_mat is not None and index in WHEEL_CANDIDATES:
                    mesh = obj.data
                    if len(mesh.polygons) != 114 or not mesh.uv_layers:
                        raise RuntimeError(f"356 wheel {index}: expected original 114-triangle UV mesh")
                    for face_id in (112, 113):
                        polygon = mesh.polygons[face_id]
                        radial = [math.hypot(mesh.vertices[k].co.y, mesh.vertices[k].co.z)
                                  for k in polygon.vertices]
                        axial = [mesh.vertices[k].co.x for k in polygon.vertices]
                        if min(radial) < 0.44 or max(axial) - min(axial) > 0.0001:
                            raise RuntimeError(f"356 wheel {index} face {face_id}: backing geometry mismatch")
                    mesh.materials.append(backing_mat)
                    backing_slot = len(mesh.materials) - 1
                    for face_id in (112, 113):
                        mesh.polygons[face_id].material_index = backing_slot
                    print(f"356 BACKING TEXTURE: article={index} faces=112/113 "
                          f"image={backing_path.name} scale={args.wheel_backing_uv_scale:g} "
                          f"alpha_threshold={args.wheel_backing_alpha_threshold:g}")
                if args.wheel_backing_hide and index in WHEEL_CANDIDATES:
                    mesh = obj.data
                    if len(mesh.polygons) != 114:
                        raise RuntimeError(f"356 wheel article {index}: expected 114 triangles; got {len(mesh.polygons)}")
                    mesh.materials.append(backing_transparent)
                    slot = len(mesh.materials) - 1
                    for face_id in (112, 113):
                        polygon = mesh.polygons[face_id]
                        radii = [math.hypot(mesh.vertices[k].co.y, mesh.vertices[k].co.z)
                                 for k in polygon.vertices]
                        if min(radii) <= 0.325:
                            raise RuntimeError(f"Wheel {index} face {face_id} is not the expected backing quad")
                        polygon.material_index = slot
                    print(f"356 BACKING HIDE: article={index} only polygons 112/113 transparent; "
                          "original mesh/UV retained")
                if args.wheel_remove_backing and index in WHEEL_CANDIDATES:
                    mesh = obj.data
                    if len(mesh.polygons) != 114:
                        raise RuntimeError(f"356 wheel {index}: expected 114 triangles; got {len(mesh.polygons)}")
                    # Validate this exact known quad before changing the Blender mesh.
                    for face_id in (112, 113):
                        face = mesh.polygons[face_id]
                        radius = [math.hypot(mesh.vertices[k].co.y, mesh.vertices[k].co.z)
                                  for k in face.vertices]
                        axial = [mesh.vertices[k].co.x for k in face.vertices]
                        if min(radius) < 0.44 or max(axial) - min(axial) > 0.0001:
                            raise RuntimeError(f"356 wheel {index} face {face_id}: unexpected geometry; refusing cleanup")
                    bm = bmesh.new()
                    try:
                        bm.from_mesh(mesh)
                        bm.faces.ensure_lookup_table()
                        bmesh.ops.delete(bm, geom=[bm.faces[112], bm.faces[113]], context="FACES")
                        bm.to_mesh(mesh)
                        mesh.update()
                    finally:
                        bm.free()
                    obj["wheel_backing_cleanup"] = "Removed original polygons 112 and 113 in Blender only"
                    print(f"356 WHEEL CLEANUP: article={index} removed=112,113 remaining={len(mesh.polygons)}")
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
    if args.wheel_strip_transparent:
        print("356 WHEEL STRIP: debug-only transparency on UV strip/crossing faces; original mesh untouched")
    if backing_mat:
        print("356 BACKING TEXTURE: testing alpha-clipped original backing faces; OBJ unchanged")
    if args.wheel_remove_backing:
        print("356 WHEEL CLEANUP: only verified square backing triangles removed in Blender; source OBJ untouched")
    if args.exterior_detail_preview:
        print(f"356 EXTERIOR DETAIL: optional candidates visible {sorted(DETAIL_ARTICLES)}; "
              "placements and original decal shaders remain unverified")
    if light_uv_dir:
        print("356 LIGHT UV: using original article UV OBJ files for 8/9/21")
        if light_materials:
            print(f"356 LIGHT TEXTURES: UV scales head={args.headlight_uv_scale:g}, "
                  f"aux={args.aux_light_uv_scale:g}, rear={args.rear_light_uv_scale:g}; "
                  "original mapping NOT verified")
    if args.wheel_backing_hide:
        print("356 BACKING HIDE: diagnostic only — transparent shader on two identified square faces per wheel")
    if args.wheel_radial_audit:
        print("356 RADIAL AUDIT: blue=inside; orange=crosses radius; red=outside; mesh unchanged")
    if args.wheel_two_materials:
        print(f"356 WHEEL TWO MATERIALS: circular=wheel image scale {args.wheel_uv_scale:g}; "
              f"strip={args.wheel_tire_texture.name} scale {args.wheel_tire_uv_scale:g}; "
              "alpha preserved; all wheel faces retained")
    if args.wheel_tire_geometry_audit:
        print("356 WHEEL GEOMETRY: cyan=circular UV region, magenta=strip, yellow=crossing; nothing hidden")
    if args.wheel_face_only:
        print("356 WHEEL FACE-ONLY: circular UV candidates use wheel artwork; other faces use provisional dark material")
    if args.wheel_uv_regions:
        print("356 WHEEL UV REGIONS: UV-space diagnostic colours ONLY; material semantics unverified")
    if wheel_uv_dir:
        print(f"356 WHEEL UV: original first-level UV OBJ geometry imported from {wheel_uv_dir}")
        if wheel_texture:
            print(f"356 WHEEL TEXTURE: experimental image {wheel_texture}; "
                  f"UV scale={args.wheel_uv_scale:g}; correct FSH assignment and face groups NOT verified")
        else:
            print("356 WHEEL UV: no texture assigned; use --crp-textures and FSH extraction to identify original image")
    if args.wheel_preview:
        print(f"356 WHEEL PREVIEW: longitudinal axle swap {'ON' if args.wheel_swap_axle_y else 'OFF'}")
        print("356 WHEEL PREVIEW: 22/106 front and 23/107 rear are independently "
              "positioned from CRP metadata when present; no assumed left/right mirroring")
    if args.door_preview:
        print("356 DOOR PREVIEW: candidates A=4/18/19/36/37/43 B=103/104/105/110/111/112; "
              "transforms provisional; compare both sides in Blender")
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
