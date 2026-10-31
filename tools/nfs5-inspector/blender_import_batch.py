"""Import local NFS5 OBJ articles with component metadata and experimental wheel placement.

Generate assembly-metadata.csv via nfs5-inspector --assembly-metadata first.
Run:
  blender --python tools/nfs5-inspector/blender_import_batch.py -- ~/gitHub/project-porsche/batch
Original game resources stay local and must not be committed.
"""
import bpy
import csv
import math
import sys

WHEEL_FORWARD_PREVIEW_OFFSET = 0.10  # Blender Y, visually calibrated on 993; unverified CRP rule
PANEL_ARTICLES = {13: "LeftDoor", 28: "Bonnet", 4: "RearLid"}
DOOR_993_CLOSED_POSITION = (0.73996, 0.84666, 0.70045)
DOOR_993_CLOSED_ROTATION = (math.pi / 2, 0.0, 0.0)
BONNET_993_CLOSED_POSITION = (0.0, 0.6854, 0.83123)
BONNET_993_CLOSED_ROTATION = (math.pi / 2, 0.0, 0.0)
from pathlib import Path


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args:
        raise SystemExit("Usage: blender --python blender_import_batch.py -- <batch-directory> [metadata.csv] [--rear-preset carrera|turbo-s|clubsport] [--lid-type 0|1|2] [--spoiler down|up] [--spoiler-compare] [--spoiler-groups-preview] [--material-preview] [--glass-light-audit] [--original-body-normals <normal-obj-file>] [--reversed-normal-parts <obj-directory>] [--wheel-geometry-diagnostic] [--wheel-group-diagnostic] [--wheel-alpha-test] [--original-wheel-textures <png-directory> <uv-obj-directory>] [--original-headlights <png-directory> <uv-obj-directory>] [--original-rearlights <png-directory> <uv-obj-directory>] [--animate-spoiler-mechanism] [--animate-spoiler] [--animate-spoiler-smooth] [--lid-underside-compare] [--rear-lid-hinge] [--animate-rear-lid] [--both-doors] [--bonnet-hinge]")
    lid_choices = {"0": 6, "1": 39, "2": 4}
    spoiler_choices = {"down": 52, "up": 53}
    def take_option(name, choices):
        if name not in args:
            return None
        index = args.index(name)
        if index + 1 >= len(args) or args[index + 1] not in choices:
            raise SystemExit(f"{name} requires one of: {', '.join(choices)}")
        value = choices[args[index + 1]]
        del args[index:index + 2]
        return value
    rear_preset = take_option("--rear-preset",
                              {"carrera": "carrera", "turbo-s": "turbo-s",
                               "clubsport": "clubsport"})
    original_body_normals_path = None
    if "--original-body-normals" in args:
        option_index = args.index("--original-body-normals")
        if option_index + 1 >= len(args) or args[option_index + 1].startswith("--"):
            raise SystemExit("--original-body-normals needs an OBJ file")
        original_body_normals_path = Path(args[option_index + 1]).expanduser()
        del args[option_index:option_index + 2]
    normal_parts_dir = None
    if "--reversed-normal-parts" in args:
        idx = args.index("--reversed-normal-parts")
        if idx + 1 >= len(args) or args[idx + 1].startswith("--"):
            raise SystemExit("--reversed-normal-parts requires an OBJ directory")
        normal_parts_dir = Path(args[idx + 1]).expanduser()
        del args[idx:idx + 2]
    original_headlight_paths = None
    if "--original-headlights" in args:
        idx = args.index("--original-headlights")
        if idx + 2 >= len(args) or args[idx + 1].startswith("--") or args[idx + 2].startswith("--"):
            raise SystemExit("--original-headlights needs <png-directory> <uv-obj-directory>")
        original_headlight_paths = (Path(args[idx + 1]).expanduser(), Path(args[idx + 2]).expanduser())
        del args[idx:idx + 3]
    original_rearlight_paths = None
    if "--original-rearlights" in args:
        idx = args.index("--original-rearlights")
        if idx + 2 >= len(args) or args[idx + 1].startswith("--") or args[idx + 2].startswith("--"):
            raise SystemExit("--original-rearlights needs <png-directory> <uv-obj-directory>")
        original_rearlight_paths = (Path(args[idx + 1]).expanduser(), Path(args[idx + 2]).expanduser())
        del args[idx:idx + 3]
    wheel_texture_paths = None
    if "--original-wheel-textures" in args:
        option_index = args.index("--original-wheel-textures")
        if len(args) <= option_index + 2 or args[option_index + 1].startswith("--") or args[option_index + 2].startswith("--"):
            raise SystemExit("--original-wheel-textures needs <texture-png-directory> <uv-obj-directory>")
        wheel_texture_paths = (Path(args[option_index + 1]).expanduser(),
                               Path(args[option_index + 2]).expanduser())
        del args[option_index:option_index + 3]
    wheel_alpha_test = "--wheel-alpha-test" in args
    if wheel_alpha_test:
        args.remove("--wheel-alpha-test")
    wheel_group_diagnostic = "--wheel-group-diagnostic" in args
    if wheel_group_diagnostic:
        args.remove("--wheel-group-diagnostic")
    wheel_geometry_diagnostic = "--wheel-geometry-diagnostic" in args
    if wheel_geometry_diagnostic:
        args.remove("--wheel-geometry-diagnostic")
    glass_light_audit = "--glass-light-audit" in args
    if glass_light_audit:
        args.remove("--glass-light-audit")
    material_preview = "--material-preview" in args
    if material_preview:
        args.remove("--material-preview")
    mechanism_spoiler = "--animate-spoiler-mechanism" in args
    if mechanism_spoiler:
        args.remove("--animate-spoiler-mechanism")
    smooth_spoiler = "--animate-spoiler-smooth" in args
    if smooth_spoiler:
        args.remove("--animate-spoiler-smooth")
    animate_spoiler = "--animate-spoiler" in args or smooth_spoiler
    if "--animate-spoiler" in args:
        args.remove("--animate-spoiler")
    if mechanism_spoiler and (animate_spoiler or rear_preset != "carrera"):
        raise SystemExit("--animate-spoiler-mechanism requires --rear-preset carrera and no other spoiler animation")
    if animate_spoiler and rear_preset != "carrera":
        raise SystemExit("--animate-spoiler requires --rear-preset carrera")
    spoiler_groups_preview = "--spoiler-groups-preview" in args
    if spoiler_groups_preview:
        args.remove("--spoiler-groups-preview")
    if spoiler_groups_preview and (rear_preset != "carrera" or animate_spoiler):
        raise SystemExit("--spoiler-groups-preview requires --rear-preset carrera without spoiler animation")
    spoiler_compare = "--spoiler-compare" in args
    if spoiler_compare:
        args.remove("--spoiler-compare")
    animate_rear_lid = "--animate-rear-lid" in args
    if animate_rear_lid:
        args.remove("--animate-rear-lid")
    requested_rear_hinge = "--rear-lid-hinge" in args
    if requested_rear_hinge:
        args.remove("--rear-lid-hinge")
    rear_hinge = requested_rear_hinge or animate_rear_lid
    underside_compare = "--lid-underside-compare" in args
    if underside_compare:
        args.remove("--lid-underside-compare")
    chosen_lid = take_option("--lid-type", lid_choices)
    if rear_hinge and chosen_lid is not None and chosen_lid != 39:
        raise SystemExit("--rear-lid-hinge currently supports only article 39 (--lid-type 1)")
    if rear_hinge:
        chosen_lid = 39
    chosen_spoiler = take_option("--spoiler", spoiler_choices)
    if rear_preset is not None:
        if chosen_lid is not None or chosen_spoiler is not None or spoiler_compare or rear_hinge:
            raise SystemExit("--rear-preset cannot be combined with manual rear selection, spoiler compare or rear-lid hinge")
        chosen_lid = {"carrera": 6, "turbo-s": 39, "clubsport": 4}[rear_preset]
        chosen_spoiler = 52 if rear_preset == "carrera" else None
        print(f"REAR PRESET: {rear_preset} (hypothetical model grouping; geometry fit unverified)")

    if spoiler_compare and chosen_spoiler is not None:
        raise SystemExit("Use --spoiler-compare without --spoiler; both states are included.")
    rear_lid_test = "--rear-lid-test" in args
    bonnet_hinge = "--bonnet-hinge" in args
    bonnet_test = "--bonnet-test" in args or bonnet_hinge
    both_doors = "--both-doors" in args
    door_hinge = "--door-hinge" in args or both_doors
    door_closed = "--door-closed" in args
    door_test = "--door-test" in args
    show_panels = "--panels" in args
    args = [item for item in args if item not in ("--panels", "--door-test", "--door-closed", "--door-hinge", "--both-doors", "--bonnet-test", "--bonnet-hinge", "--rear-lid-test")]
    batch = Path(args[0]).expanduser()
    manifest = batch / "manifest.csv"
    metadata = Path(args[1]).expanduser() if len(args) > 1 else batch / "assembly-metadata.csv"
    if not manifest.is_file() or not metadata.is_file():
        raise SystemExit("Missing manifest.csv or assembly-metadata.csv; run --assembly-metadata first")
    with metadata.open(newline="") as stream:
        meta = {int(row["article"]): row for row in csv.DictReader(stream)}

    collection = bpy.data.collections.new("NFS5 Porsche 993 - components")
    bpy.context.scene.collection.children.link(collection)
    # OBJ vertices are already correctly oriented; remap only CRP translations.
    root = bpy.data.objects.new("Porsche_993_CRP_to_Blender", None)
    collection.objects.link(root)
    root.rotation_euler = (0.0, 0.0, 0.0)
    root["coordinate_conversion"] = "mesh unchanged; translation (x,y,z) -> (x,z,y)"
    initially_visible = {5, 20}  # hide movable panels for alignment
    # The TypeIndex=1 wheel meshes are variants, not left/right positions.
    # Opposite-side mirroring is an unverified reconstruction hypothesis.
    wheels = {}
    panels = {}
    rear_variants = {}
    imported = missing = 0
    with manifest.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["status"] != "exported":
                continue
            index = int(row["article"])
            file = batch / row["file_or_reason"]
            if not file.is_file():
                missing += 1
                continue
            previous = set(bpy.data.objects.keys())
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=str(file))
            elif hasattr(bpy.ops.import_scene, "obj"):
                bpy.ops.import_scene.obj(filepath=str(file))
            else:
                raise RuntimeError("Blender OBJ importer unavailable")
            objects = [o for o in bpy.data.objects if o.name not in previous]
            for obj in objects:
                obj.name = f"{index:03d}_{row['name']}"
                for old in list(obj.users_collection):
                    old.objects.unlink(obj)
                collection.objects.link(obj)
                obj.parent = root
                info = meta.get(index)
                obj["crp_article"] = index
                obj["crp_name"] = row["name"]
                if info:
                    for key in ("geom_index", "type_index", "geom_type",
                                "wheel_type", "level_index", "anim_type"):
                        obj["crp_" + key] = int(info[key])
                    if int(info["has_transform"]):
                        obj["crp_pivot"] = [float(info[key]) for key in ("tx", "ty", "tz")]
                visible = index in initially_visible or index in (46, 47) or (show_panels and index in PANEL_ARTICLES)
                obj.hide_set(not visible)
                obj.hide_render = not visible
                if index in (46, 47) and info and int(info["has_transform"]):
                    obj.location = (float(info["tx"]), float(info["tz"]) + WHEEL_FORWARD_PREVIEW_OFFSET, float(info["ty"]))
                    wheels[index] = obj
                if index in (4, 6, 39, 52, 53):
                    rear_variants.setdefault(index, []).append(obj)
                if index in PANEL_ARTICLES and info and int(info["has_transform"]):
                    panels.setdefault(index, []).append(obj)
            imported += 1

    # CRP WheelFront (46) and WheelRear (47) mesh widths are correct, but
    # applying their raw Z translations as Blender Y put them on opposite
    # axles relative to the correctly oriented body. Exchange ONLY Y axle
    # positions; retain each article's original mesh, lateral X, and height Z.
    if 46 in wheels and 47 in wheels:
        front_y = wheels[46].location.y
        rear_y = wheels[47].location.y
        wheels[46].location.y = rear_y
        wheels[47].location.y = front_y
        print("WHEEL AXLES: front/rear longitudinal positions exchanged; meshes and lateral offsets retained.")
    else:
        print("WARNING: axle correction skipped: both articles 46 and 47 are required.")

    for index, label in ((46, "Front"), (47, "Rear")):
        source = wheels.get(index)
        if source is None:
            print(f"WARNING: wheel article {index} missing")
            continue
        mirror = source.copy()
        mirror.data = source.data
        mirror.name = f"{index:03d}_{label}_opposite_TEST_MIRROR"
        collection.objects.link(mirror)
        mirror.parent = root
        mirror.location.x = -source.location.x
        mirror.scale.x = -source.scale.x
        mirror["crp_mirrored_hypothesis"] = True
        mirror.hide_set(False)
        mirror.hide_render = False

    # Panel meshes appear to use mixed conventions. Do not change their raw
    # vertices or add their pivots as another translation. Instead create
    # independent hinge empties at candidate CRP pivots; parenting with a
    # preserved world matrix leaves the closed geometry exactly where it was.
    # Rotating a hinge is deliberately exploratory until panel geometry
    # coordinate conventions and hinge axes are verified.
    bpy.context.view_layer.update()
    from mathutils import Vector
    for index, label in PANEL_ARTICLES.items():
        pieces = panels.get(index, [])
        if not pieces:
            print(f"Panel {index} {label}: missing mesh or transform; skipped hinge")
            continue
        point = pieces[0]["crp_pivot"]
        hinge = bpy.data.objects.new(f"HINGE_TEST_{label}_{index:03d}", None)
        collection.objects.link(hinge)
        hinge.parent = root
        hinge.location = (point[0], point[2], point[1])
        hinge["crp_article"] = index
        hinge["crp_pivot"] = list(point)
        hinge["experimental_hinge"] = True
        bpy.context.view_layer.update()
        for obj in pieces:
            old_world = obj.matrix_world.copy()
            obj.parent = hinge
            obj.matrix_world = old_world
            obj.hide_set(not show_panels)
            obj.hide_render = not show_panels

    if door_test or door_closed or door_hinge:
        # Door-only A/B test: retain the raw hinge assembly but hide it.
        # Show an independent linked-mesh preview translated by the mapped
        # CRP component matrix. No modification to exported geometry.
        door_pieces = panels.get(13, [])
        if door_pieces:
            raw = door_pieces[0]
            raw_coords = [raw.data.vertices[i].co for i in range(len(raw.data.vertices))]
            if raw_coords:
                bounds_lo = tuple(min(v[k] for v in raw_coords) for k in range(3))
                bounds_hi = tuple(max(v[k] for v in raw_coords) for k in range(3))
                pivot = raw["crp_pivot"]
                mapped = (pivot[0], pivot[2], pivot[1])
                print(f"DOOR article 13 raw local vertex bounds: {bounds_lo} .. {bounds_hi}")
                print(f"DOOR article 13 CRP pivot: {tuple(pivot)}; mapped Blender: {mapped}")
                print("DOOR hypothesis: translated bounds = raw bounds + mapped pivot")
                print(f"DOOR hypothesis bounds: {tuple(bounds_lo[k]+mapped[k] for k in range(3))} .. {tuple(bounds_hi[k]+mapped[k] for k in range(3))}")
                candidate = raw.copy()
                candidate.data = raw.data
                candidate.name = "013_DoorOut_TRANSLATED_TEST"
                collection.objects.link(candidate)
                candidate.parent = root
                candidate.matrix_parent_inverse.identity()
                candidate.location = DOOR_993_CLOSED_POSITION if (door_closed or door_hinge) else mapped
                candidate.rotation_euler = DOOR_993_CLOSED_ROTATION if (door_closed or door_hinge) else (0, 0, 0)
                candidate.scale = (1, 1, 1)
                candidate["crp_translation_test"] = True
                candidate.hide_set(False)
                candidate.hide_render = False
                if door_hinge:
                    # Compute the front edge from the actual *closed* geometry,
                    # then put an independent hinge at the A-pillar side.
                    # For this calibrated door the A-pillar/front hinge is at maximum Y.
                    from mathutils import Vector
                    bpy.context.view_layer.update()
                    bounds = [candidate.matrix_world @ Vector(c) for c in candidate.bound_box]
                    front_y = max(point.y for point in bounds)
                    low_z = min(point.z for point in bounds)
                    high_z = max(point.z for point in bounds)
                    hinge = bpy.data.objects.new("HINGE_993_LeftDoor_CLOSED_REFERENCE", None)
                    collection.objects.link(hinge)
                    hinge.parent = root
                    hinge.location = (candidate.location.x, front_y, (low_z + high_z) / 2)
                    hinge.empty_display_type = 'ARROWS'
                    hinge.empty_display_size = 0.22
                    hinge["hinge_axis"] = "Blender Z (vertical)"
                    hinge["hinge_status"] = "approximate from visually calibrated door bounds"
                    hinge["closed_angle_degrees"] = 0.0
                    bpy.context.view_layer.update()
                    matrix = candidate.matrix_world.copy()
                    candidate.parent = hinge
                    candidate.matrix_world = matrix
                    if both_doors:
                        # Opposite door is a mirrored preview, not yet verified
                        # against a native right-hand CRP component.
                        # Mirror the entire closed-door transform across X,
                        # then parent to an independent, mirrored front hinge.
                        from mathutils import Matrix
                        opposite = candidate.copy()
                        opposite.data = candidate.data
                        opposite.name = "013_DoorOut_Opposite_MIRRORED_TEST"
                        collection.objects.link(opposite)
                        opposite.parent = None
                        bpy.context.view_layer.update()
                        reflection = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
                        opposite_world = reflection @ candidate.matrix_world
                        right_hinge = bpy.data.objects.new("HINGE_993_OppositeDoor_MIRRORED_TEST", None)
                        collection.objects.link(right_hinge)
                        right_hinge.parent = root
                        right_hinge.location = (-hinge.location.x, hinge.location.y, hinge.location.z)
                        right_hinge.empty_display_type = 'ARROWS'
                        right_hinge.empty_display_size = 0.22
                        right_hinge["hinge_status"] = "mirrored test; NOT decoded as an original right door"
                        right_hinge["hinge_axis"] = "Blender Z (vertical)"
                        bpy.context.view_layer.update()
                        opposite.parent = right_hinge
                        opposite.matrix_world = opposite_world
                        opposite.hide_set(False)
                        opposite.hide_render = False
                        opposite["crp_mirrored_hypothesis"] = True
                        print("OPPOSITE DOOR: mirrored geometry and independent A-pillar hinge (unverified).")
                    print(f"DOOR HINGE candidate at {tuple(round(x, 4) for x in hinge.location)}")
                    print("Rotate HINGE_993_LeftDoor_CLOSED_REFERENCE around local Z to open.")
                    print("Rotation Z = 0 is the verified closed reference; axis and pivot provisional.")
                for original in door_pieces:
                    original.hide_set(True)
                    original.hide_render = True
                print("DOOR calibrated closed preview visible." if door_closed else "DOOR translated test visible. Original door under hinge remains hidden.")
        else:
            print("DOOR TEST: article 13 absent; verify batch and metadata.")

    if bonnet_test:
        # Article 28: visually isolate two hypotheses without modifying raw
        # mesh data. Raw-only is retained hidden; translation-only is visible.
        # Do not assume these represent the actual closed/open positions.
        bonnet_pieces = panels.get(28, [])
        if bonnet_pieces:
            for raw in bonnet_pieces:
                raw.hide_set(True)
                raw.hide_render = True
                pivot = raw["crp_pivot"]
                mapped = (pivot[0], pivot[2], pivot[1])
                bounds = [raw.data.vertices[i].co for i in range(len(raw.data.vertices))]
                if bounds:
                    lo = tuple(min(vertex[k] for vertex in bounds) for k in range(3))
                    hi = tuple(max(vertex[k] for vertex in bounds) for k in range(3))
                    print(f"BONNET 28 raw local bounds: {lo} .. {hi}")
                    print(f"BONNET 28 raw CRP pivot: {tuple(pivot)}")
                    print(f"BONNET 28 mapped pivot: {mapped}")
                    print(f"BONNET 28 translation-only bounds: {tuple(lo[k]+mapped[k] for k in range(3))} .. {tuple(hi[k]+mapped[k] for k in range(3))}")
                candidate = raw.copy()
                candidate.data = raw.data
                candidate.name = "028_HoodOut_TRANSLATED_TEST"
                collection.objects.link(candidate)
                candidate.parent = root
                candidate.matrix_parent_inverse.identity()
                candidate.location = BONNET_993_CLOSED_POSITION if bonnet_hinge else mapped
                candidate.rotation_euler = BONNET_993_CLOSED_ROTATION if bonnet_hinge else (0.0, 0.0, 0.0)
                candidate.scale = (1.0, 1.0, 1.0)
                candidate["bonnet_translation_hypothesis"] = not bonnet_hinge
                candidate.hide_set(False)
                candidate.hide_render = False
                if bonnet_hinge:
                    # Windscreen-facing edge is the rear of the closed bonnet:
                    # vehicle front is +Y, so the hinge goes at minimum Y.
                    bpy.context.view_layer.update()
                    world_bounds = [candidate.matrix_world @ Vector(c) for c in candidate.bound_box]
                    rear_y = min(p.y for p in world_bounds)
                    mid_z = (min(p.z for p in world_bounds) + max(p.z for p in world_bounds)) / 2
                    hinge = bpy.data.objects.new("HINGE_993_Bonnet_CLOSED_REFERENCE", None)
                    collection.objects.link(hinge)
                    hinge.parent = root
                    hinge.location = (0.0, rear_y, mid_z)
                    hinge.empty_display_type = 'ARROWS'
                    hinge.empty_display_size = 0.25
                    hinge["hinge_axis"] = "Blender X (across car)"
                    hinge["hinge_status"] = "estimated from closed bonnet rear bounding edge"
                    hinge["closed_angle_degrees"] = 0.0
                    bpy.context.view_layer.update()
                    closed_world = candidate.matrix_world.copy()
                    candidate.parent = hinge
                    candidate.matrix_world = closed_world
                    print(f"BONNET HINGE candidate at {tuple(round(v, 5) for v in hinge.location)}")
                    print("Rotate HINGE_993_Bonnet_CLOSED_REFERENCE around X, e.g. +/-35 deg")
            if bonnet_hinge:
                print("BONNET: calibrated closed position with adjustable rear hinge (test).")
            else:
                print("BONNET: translated test copy visible; rotation and closed placement unverified.")
        else:
            print("BONNET TEST: missing article 28; check batch and metadata.")

    if rear_lid_test:
        # Isolate article 4 without guessing closed positioning or hinge axis.
        # As with the first bonnet test, compare untranslated and CRP-mapped
        # translation candidates using the same exported mesh data.
        rear_pieces = panels.get(4, [])
        if not rear_pieces:
            print("REAR LID TEST: article 4 missing; check OBJ batch and metadata.")
        for raw in rear_pieces:
            raw.hide_set(True)
            raw.hide_render = True
            point = raw["crp_pivot"]
            mapped = (point[0], point[2], point[1])
            vertices = [v.co for v in raw.data.vertices]
            if not vertices:
                print("REAR LID TEST: article 4 has no vertices")
                continue
            lo = tuple(min(v[k] for v in vertices) for k in range(3))
            hi = tuple(max(v[k] for v in vertices) for k in range(3))
            print(f"REAR LID 4 raw local bounds: {lo} .. {hi}")
            print(f"REAR LID 4 raw CRP pivot: {tuple(point)}")
            print(f"REAR LID 4 mapped pivot: {mapped}")
            print(f"REAR LID 4 translation-only bounds: {tuple(lo[k]+mapped[k] for k in range(3))} .. {tuple(hi[k]+mapped[k] for k in range(3))}")
            candidate = raw.copy()
            candidate.data = raw.data
            candidate.name = "004_TrunkOut2_TRANSLATED_TEST"
            collection.objects.link(candidate)
            candidate.parent = root
            candidate.matrix_parent_inverse.identity()
            candidate.location = mapped
            candidate.rotation_euler = (0.0, 0.0, 0.0)
            candidate.scale = (1.0, 1.0, 1.0)
            candidate["rear_lid_translation_hypothesis"] = True
            candidate.hide_set(False)
            candidate.hide_render = False
        print("REAR LID: translation-only candidate visible; lid/spoiler geometry variants not yet resolved.")

    # Component groups decoded from BaseInfo:
    # lid GeomIndex=16 TypeIndex=0/1/2; spoiler GeomIndex=42 TypeIndex=1/2.
    # Keep selection independent. This pose is an UNCALIBRATED reference
    # rotation, not a claim about the original game's default configuration.
    if chosen_lid is not None or chosen_spoiler is not None:
        if rear_preset is not None:
            root["rear_preset_hypothesis"] = rear_preset
            print("REAR PRESET: source meshes unchanged; calibrated closed position not guaranteed.")
        for index in (4, 6, 39, 52, 53):
            for raw in rear_variants.get(index, []):
                raw.hide_set(True)
                raw.hide_render = True

        for group_name, selected in (("lid", chosen_lid), ("spoiler", chosen_spoiler)):
            if selected is None:
                continue
            pieces = rear_variants.get(selected, [])
            if not pieces:
                print(f"WARNING: selected {group_name} article {selected} missing from exported batch")
                continue
            for raw in pieces:
                pivot = raw.get("crp_pivot")
                if pivot is None:
                    print(f"WARNING: selected {group_name} article {selected} has no CRP pivot")
                    continue
                copy = raw.copy()
                copy.data = raw.data
                copy.name = f"REAR_{group_name.upper()}_{selected:03d}_REFERENCE_TEST"
                collection.objects.link(copy)
                copy.parent = root
                copy.matrix_parent_inverse.identity()
                if rear_preset == "carrera" and selected == 52:
                    # User-verified visual alignment of lowered Carrera spoiler,
                    # recovered after Blender crash on 2026-10-24.
                    copy.location = (0.0, -1.39, 0.85)
                elif rear_preset:
                    copy.location = (pivot[0], pivot[2] - 2.66, pivot[1])
                else:
                    copy.location = (pivot[0], pivot[2], pivot[1])
                copy.rotation_euler = (math.pi / 2, 0.0, 0.0)
                copy.scale = (1.0, 1.0, 1.0)
                copy["crp_variant_group"] = group_name
                copy["crp_variant_article"] = selected
                copy["pose_status"] = (
                    "visually calibrated Carrera SpoilerDown at (0,-1.39,0.85), 90deg X"
                    if rear_preset == "carrera" and selected == 52
                    else "provisional rear-deck -2.66 Y translation" if rear_preset
                    else "uncalibrated; mapped translation and 90-degree X"
                )
                copy.hide_set(False)
                copy.hide_render = False
            print(f"REAR {group_name.upper()}: selected article {selected}, orientation/placement uncalibrated.")

    if animate_spoiler:
        # A discrete visibility switch between fully modelled states, not
        # a physical interpolation. Both objects share the visually checked
        # Carrera spoiler-down transform (raised-state fit still provisional).
        down = next((obj for obj in collection.objects
                     if obj.get("crp_variant_group") == "spoiler"
                     and obj.get("crp_variant_article") == 52), None)
        sources = rear_variants.get(53, [])
        if down is None or not sources:
            print("WARNING: spoiler animation needs articles 52 and 53; skipped")
        else:
            up = sources[0].copy()
            up.data = sources[0].data
            up.name = "REAR_SPOILER_053_RAISED_ANIMATED"
            collection.objects.link(up)
            up.parent = root
            up.matrix_parent_inverse.identity()
            up.location = down.location.copy()
            up.rotation_euler = down.rotation_euler.copy()
            up.scale = down.scale.copy()
            up["crp_variant_group"] = "spoiler"
            up["crp_variant_article"] = 53
            up["pose_status"] = "same as calibrated lowered spoiler; raised fit provisional"
            # Do not keyframe hide_viewport: Blender can stop evaluating the
            # disabled object's world transform. Instead switch visibility via
            # scale keys (0 or original scale) and hide_render for renders.
            # Constant interpolation ensures no scaling between states.
            down_scale = down.scale.copy()
            up_scale = up.scale.copy()
            down.hide_set(False)
            up.hide_set(False)
            down.hide_viewport = False
            up.hide_viewport = False
            # A rigid lift is a visual approximation; the different meshes
            # cannot be vertex-morphed without a topology correspondence.
            # Hand off at frames 31 / 76, then move the complete raised mesh.
            if smooth_spoiler:
                drop = 0.10  # metres; experimental vertical lift
                state_keys = ((1, False), (30, False), (31, True),
                              (75, True), (76, False), (100, False))
            else:
                state_keys = ((1, False), (20, False), (21, True),
                              (75, True), (76, False), (100, False))
            for frame, raised in state_keys:
                for obj, active, normal_scale in (
                    (down, not raised, down_scale),
                    (up, raised, up_scale),
                ):
                    obj.scale = normal_scale if active else (0.0, 0.0, 0.0)
                    obj.hide_render = not active
                    obj.keyframe_insert(data_path="scale", frame=frame,
                                        group="Carrera spoiler states")
                    obj.keyframe_insert(data_path="hide_render", frame=frame,
                                        group="Carrera spoiler states")
            if smooth_spoiler:
                base_z = down.location.z
                for frame, z in ((1, base_z-drop), (30, base_z-drop),
                                 (31, base_z-drop), (45, base_z),
                                 (60, base_z), (75, base_z),
                                 (76, base_z-drop), (100, base_z-drop)):
                    up.location.z = z
                    up.keyframe_insert(data_path="location", index=2, frame=frame,
                                       group="Carrera spoiler lift")
                up.location.z = base_z - drop
            for obj in (down, up):
                if obj.animation_data and obj.animation_data.action:
                    action = obj.animation_data.action
                    # Blender 4.x exposes action.fcurves; Blender 5.x may use
                    # layered actions, but adjacent keys still give exact
                    # on/off states at the prescribed integer frames.
                    for curve in getattr(action, "fcurves", []):
                        if curve.data_path == "scale":
                            for point in curve.keyframe_points:
                                point.interpolation = 'CONSTANT'
            down.hide_render = False
            up.hide_render = True
            scene = bpy.context.scene
            scene.frame_start = 1
            scene.frame_end = 100
            scene.frame_set(1)
            if smooth_spoiler:
                print("CARRERA SPOILER EXPERIMENT: mesh handoff at 31; rigid +0.10m lift through frame 45.")
                print("NOTE: closing handoff at 76 is still abrupt; this does not reproduce real mechanism.")
            else:
                print("CARRERA SPOILER: down frames 1-20, up 21-75, down 76-100.")
            print("NOTE: discrete scale-based visibility state swap; no mechanical interpolation.")

    if mechanism_spoiler:
        # Experimental reconstruction from the raised endpoint (article 53).
        # 0x1000/1003 = presumed triangular supports (6 triangles per side).
        # Remaining groups = moving panel. These assignments are provisional.
        # No topology morph between articles 52 and 53 is attempted.
        sources = rear_variants.get(53, [])
        lowered = next((o for o in collection.objects
                        if o.get("crp_variant_group") == "spoiler"
                        and o.get("crp_variant_article") == 52), None)
        if not sources or lowered is None:
            print("WARNING: mechanism preview requires spoiler articles 52 and 53")
        else:
            raw = sources[0]
            face_counts = (6, 4, 40, 6, 4, 40)
            if len(raw.data.polygons) != sum(face_counts):
                print("WARNING: article 53 polygon count differs from expected 100; mechanism skipped")
            else:
                # Don't disable viewport evaluation on animated pieces.
                lowered.hide_set(True)
                lowered.hide_render = True
                faces = list(raw.data.polygons)
                coords = [tuple(v.co) for v in raw.data.vertices]
                face_groups = []
                start = 0
                for count in face_counts:
                    face_groups.append([tuple(p.vertices) for p in faces[start:start + count]])
                    start += count
                travel = 0.10  # metres; placeholder, not measured from Porsche
                yvals = [coords[i][1] for g in (0, 3) for face in face_groups[g] for i in face]
                bottom, top = min(yvals), max(yvals)
                for role, chosen in (("PANEL", (1, 2, 4, 5)), ("SUPPORT", (0, 3))):
                    indices = sorted({i for g in chosen for face in face_groups[g] for i in face})
                    remap = {old: j for j, old in enumerate(indices)}
                    local_faces = [tuple(remap[i] for i in face)
                                   for g in chosen for face in face_groups[g]]
                    name = "SPOILER_MECHANISM_" + role
                    mesh = bpy.data.meshes.new(name)
                    mesh.from_pydata([coords[i] for i in indices], [], local_faces)
                    mesh.update()
                    obj = bpy.data.objects.new(name, mesh)
                    collection.objects.link(obj)
                    obj.parent = root
                    obj.matrix_parent_inverse.identity()
                    obj.location = lowered.location.copy()
                    obj.rotation_euler = lowered.rotation_euler.copy()
                    obj.scale = lowered.scale.copy()
                    obj["mechanism_status"] = "experimental group split; travel and grouping provisional"
                    obj.hide_set(False)
                    obj.hide_render = False
                    if role == "PANEL":
                        base = obj.location.z
                        for frame, z in ((1, base-travel), (20, base-travel),
                                         (45, base), (75, base), (100, base-travel)):
                            obj.location.z = z
                            obj.keyframe_insert(data_path="location", index=2, frame=frame,
                                                group="Carrera experimental panel lift")
                    else:
                        # With +90 deg X, CRP Y maps to Blender Z.
                        # Vertices near the bottom remain anchored; vertices
                        # toward the upper edge follow the moving panel.
                        obj.shape_key_add(name="Extended", from_mix=False)
                        key = obj.shape_key_add(name="Retracted", from_mix=False)
                        span = max(top-bottom, 1e-6)
                        for j, original in enumerate(indices):
                            weight = max(0.0, min(1.0, (coords[original][1]-bottom)/span))
                            key.data[j].co.y -= travel * weight
                        for frame, influence in ((1, 1.0), (20, 1.0),
                                                 (45, 0.0), (75, 0.0), (100, 1.0)):
                            key.value = influence
                            key.keyframe_insert(data_path="value", frame=frame,
                                                group="Carrera experimental flexible support")
                scene = bpy.context.scene
                scene.frame_start, scene.frame_end = 1, 100
                scene.frame_set(1)
                print("SPOILER MECHANISM: panel lifts 10 cm; triangular supports deform, lower vertices anchored.")
                print("EXPERIMENTAL: not guaranteed flush at frame 1; does not reconstruct actual 993 linkage.")

    if spoiler_groups_preview:
        # Diagnostic only: OBJ export emits polygons sequentially from the
        # level-1 CRP descriptors 0x1000..0x1005. Isolate face runs, not
        # arbitrary vertex-index ranges (the groups share vertices).
        counts = (6, 4, 40, 6, 4, 40)
        palette = ((0.92, 0.19, 0.15, 1), (0.96, 0.65, 0.12, 1),
                   (0.18, 0.58, 0.98, 1), (0.63, 0.24, 0.83, 1),
                   (0.17, 0.8, 0.43, 1), (0.96, 0.35, 0.66, 1))
        for obj in collection.objects:
            if obj.type == 'MESH':
                obj.hide_set(True)
                obj.hide_render = True
        for article, lateral_offset, state in ((52, -1.1, "DOWN"),
                                                (53, 1.1, "UP")):
            sources = rear_variants.get(article, [])
            if len(sources) != 1:
                print(f"WARNING: expected one source mesh for spoiler {article}; got {len(sources)}")
                continue
            raw = sources[0]
            faces = list(raw.data.polygons)
            if len(faces) != sum(counts):
                print(f"WARNING: spoiler {article} has {len(faces)} faces; expected {sum(counts)}. Group extraction skipped.")
                continue
            vertices = [tuple(v.co) for v in raw.data.vertices]
            start = 0
            for group, (count, rgba) in enumerate(zip(counts, palette), start=1):
                polys = [tuple(face.vertices) for face in faces[start:start + count]]
                start += count
                name = f"SPOILER_{state}_{article:03d}_GROUP_{group}_0x{0x0fff+group:04X}"
                mesh = bpy.data.meshes.new(name)
                mesh.from_pydata(vertices, [], polys)
                mesh.update()
                part = bpy.data.objects.new(name, mesh)
                collection.objects.link(part)
                part.parent = root
                part.matrix_parent_inverse.identity()
                part.location = (lateral_offset, -1.39, 0.85)
                part.rotation_euler = (math.pi / 2, 0.0, 0.0)
                mat = bpy.data.materials.new(f"SPOILER_GROUP_{group}_COLOR")
                mat.diffuse_color = rgba
                mesh.materials.append(mat)
                part["crp_variant_article"] = article
                part["crp_polygon_descriptor"] = f"0x{0x0fff+group:04X}"
                part["diagnostic"] = "level-1 OBJ face-run segmentation; lateral offset for visual comparison"
                part.hide_set(False)
                part.hide_render = False
            print(f"SPOILER GROUPS {state}: 6 separate meshes, total {sum(counts)} triangles.")
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.color_type = 'MATERIAL'
        print("SPOILER GROUP PREVIEW: DOWN on left (X=-1.1), UP on right (X=+1.1).")
        print("Six consistent descriptor colours per state. All other meshes hidden.")
        print("Diagnostic segmentation only; original source meshes unchanged.")

    if spoiler_compare:
        # Both spoiler states share the level-1 CRP translation. Compare the
        # geometry in the same provisional rear-deck pose; never infer a
        # mechanical hinge or interpolation from distinct mesh states.
        for index in (52, 53):
            pieces = rear_variants.get(index, [])
            if not pieces:
                print(f"WARNING: missing spoiler article {index} in batch")
            for raw in pieces:
                raw.hide_set(True)
                raw.hide_render = True
                pivot = raw.get("crp_pivot")
                if pivot is None:
                    print(f"WARNING: spoiler article {index} missing CRP pivot")
                    continue
                preview = raw.copy()
                preview.data = raw.data
                preview.name = f"SPOILER_COMPARE_{index:03d}_{'DOWN' if index == 52 else 'UP'}"
                collection.objects.link(preview)
                preview.parent = root
                preview.matrix_parent_inverse.identity()
                preview.location = (float(pivot[0]), float(pivot[2]) - 2.66, float(pivot[1]))
                preview.rotation_euler = (math.pi / 2, 0.0, 0.0)
                preview.scale = (1.0, 1.0, 1.0)
                preview["comparison_status"] = "provisional -2.66 Y offset from lid alignment; no animation"
                preview.hide_set(index != 52)
                preview.hide_render = index != 52
        print("SPOILER COMPARE: Down (52) visible, Up (53) hidden.")
        print("Toggle both objects' viewport AND render visibility to compare states.")
        print("Both use the provisional rear-lid longitudinal offset -2.66m.")

    if rear_hinge:
        # Hinge moved to the rear-window edge in the 2026-10-24 Blender test.
        # This is a provisional hinge and closed seam still needs inspection.
        # Reported opening rotation was 30 radians (1718.87 degrees), so
        # never persist that angle as the default rest pose.
        # Keep the rest pose and opening motion distinct by parenting the
        # positioned mesh to the hinge, whose rotation remains zero.
        hinge_position = (0.0, -1.422851, 0.88027)
        local_lid_position = (0.0, 0.093211, -0.00143)
        candidates = [obj for obj in collection.objects
                      if obj.get("crp_variant_group") == "lid"
                      and obj.get("crp_variant_article") == 39]
        if not candidates:
            print("REAR HINGE: no article 39 preview available")
        for candidate in candidates:
            hinge = bpy.data.objects.new("HINGE_993_RearLid39_PROVISIONAL", None)
            collection.objects.link(hinge)
            hinge.parent = root
            hinge.location = hinge_position
            hinge.rotation_euler = (0.0, 0.0, 0.0)
            hinge.empty_display_type = 'ARROWS'
            hinge.empty_display_size = 0.25
            hinge["hinge_axis"] = "Blender X"
            hinge["hinge_status"] = "rear-window edge pivot from 2026-10-24; closed seam not verified"
            hinge["rest_angle_degrees"] = 0.0
            candidate.parent = hinge
            candidate.matrix_parent_inverse.identity()
            candidate.location = local_lid_position
            candidate.rotation_euler = (math.pi / 2, 0.0, 0.0)
            candidate.scale = (1.0, 1.0, 1.0)
            candidate["pose_status"] = "rear-window edge hinge; closed pose provisional, 2026-10-24"
            bpy.context.view_layer.update()
            if animate_rear_lid:
                # Blender animation timeline: 1-20 closed, 45 open,
                # 75 hold, 100 closed. -30 degrees visually validated.
                for frame, angle in ((1, 0), (20, 0), (45, -30),
                                     (75, -30), (100, 0)):
                    hinge.rotation_euler.x = math.radians(angle)
                    hinge.keyframe_insert(data_path="rotation_euler", index=0,
                                          frame=frame, group="Rear engine lid")
                hinge.rotation_euler.x = 0.0
                scene = bpy.context.scene
                scene.frame_start = 1
                scene.frame_end = 100
                scene.frame_set(1)
                print("REAR HINGE ANIMATION: frames 1-20 closed, 45-75 open (-30 deg), 100 closed.")
            print(f"REAR HINGE: restored {tuple(hinge.location)}")
            print("Lid at 90 degrees local X; hinge at zero. Test hinge X in DEGREES: +/-20 to 30.")
        print("REAR HINGE: reproducible provisional fit; original CRP data unchanged.")

    if underside_compare:
        # Show identical placement/orientation for the two potential standard lids.
        # Hide the entire car to allow underside inspection without occlusion.
        for obj in collection.objects:
            if obj.type == 'MESH':
                obj.hide_set(True)
                obj.hide_render = True
        for article, offset, label in (
            (6, -1.05, "TYPE0_BASIC"),
            (39, 1.05, "TYPE1_DETAILED"),
        ):
            for raw in rear_variants.get(article, []):
                pivot = raw.get("crp_pivot")
                if pivot is None:
                    print(f"WARNING: underside compare: missing pivot for article {article}")
                    continue
                candidate = raw.copy()
                candidate.data = raw.data
                candidate.name = f"COMPARE_UNDERSIDE_{article:03d}_{label}"
                collection.objects.link(candidate)
                candidate.parent = root
                candidate.matrix_parent_inverse.identity()
                candidate.location = (float(pivot[0]) + offset, float(pivot[2]), float(pivot[1]))
                candidate.rotation_euler = (math.pi / 2, 0.0, 0.0)
                candidate.scale = (1.0, 1.0, 1.0)
                candidate["comparison_role"] = label
                candidate["pose_status"] = "same provisional orientation; X offset only"
                candidate.hide_set(False)
                candidate.hide_render = False
        print("LID UNDERSIDE COMPARE: article 6 at X=-1.05, article 39 at X=+1.05.")
        print("All other meshes hidden. Orbit Blender view underneath to compare underside faces.")
        print("Candidate positions use provisional mapping, not calibrated showroom-open poses.")


    if original_body_normals_path is not None:
        if not original_body_normals_path.is_file():
            raise FileNotFoundError(f"Normals-aware body OBJ not found: {original_body_normals_path}")
        original_body = next((obj for obj in collection.objects
                              if obj.type == 'MESH' and obj.get("crp_article") == 5), None)
        if original_body is None:
            raise RuntimeError("Body article 5 is absent from the imported assembly")
        existing_names = set(bpy.data.objects.keys())
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(original_body_normals_path))
        elif hasattr(bpy.ops.import_scene, "obj"):
            bpy.ops.import_scene.obj(filepath=str(original_body_normals_path))
        else:
            raise RuntimeError("OBJ importer unavailable")
        temporary = [obj for obj in bpy.data.objects if obj.name not in existing_names
                     and obj.type == 'MESH']
        if len(temporary) != 1:
            raise RuntimeError("Expected exactly one normals-aware body mesh")
        replacement = temporary[0].data
        if len(replacement.vertices) != len(original_body.data.vertices) or len(replacement.polygons) != len(original_body.data.polygons):
            raise RuntimeError("Body normal mesh topology differs from current assembly; aborting replacement")
        replacement.name = "NFS5_Body_Original_Vertex_Normals_Experimental"
        for polygon in replacement.polygons:
            polygon.use_smooth = True
        original_body.data = replacement
        bpy.data.objects.remove(temporary[0], do_unlink=True)
        print(f"ORIGINAL BODY NORMALS: replaced article 5 mesh ({len(replacement.vertices)} vertices, "
              f"{len(replacement.polygons)} triangles); smooth shading enabled, source normal import subject to Blender OBJ interpretation.")

    if normal_parts_dir is not None:
        # Preserve all object transforms, parenting, hinge constraints and wheel meshes.
        # The same article may appear more than once (e.g. a mirrored door).
        for article in (5, 20, 13, 28):
            source = normal_parts_dir / f"article-{article}-reversed.obj"
            if not source.is_file():
                raise FileNotFoundError(f"Missing reversed-normal article OBJ: {source}")
            destinations = [o for o in collection.objects
                            if o.type == 'MESH' and o.get('crp_article') == article]
            if not destinations:
                print(f"REVERSED NORMAL PARTS: article {article} not present; skipped")
                continue
            previous_names = set(bpy.data.objects.keys())
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=str(source))
            elif hasattr(bpy.ops.import_scene, "obj"):
                bpy.ops.import_scene.obj(filepath=str(source))
            else:
                raise RuntimeError("Blender OBJ importer unavailable")
            temporary = [o for o in bpy.data.objects
                         if o.name not in previous_names and o.type == 'MESH']
            if len(temporary) != 1:
                raise RuntimeError(f"Expected one normals mesh for article {article}, got {len(temporary)}")
            mesh = temporary[0].data
            target = destinations[0]
            if len(mesh.vertices) != len(target.data.vertices) or len(mesh.polygons) != len(target.data.polygons):
                raise RuntimeError(f"Article {article} topology mismatch: "
                                   f"imported {len(mesh.vertices)}/{len(mesh.polygons)}, "
                                   f"assembly {len(target.data.vertices)}/{len(target.data.polygons)}")
            mesh.name = f"NFS5_article_{article}_reversed_normals_EXPERIMENT"
            for face in mesh.polygons:
                face.use_smooth = True
            original_mesh = target.data
            for obj in collection.objects:
                if obj.type == 'MESH' and (obj.get('crp_article') == article or obj.data == original_mesh):
                    obj.data = mesh
            bpy.data.objects.remove(temporary[0], do_unlink=True)
            print(f"REVERSED NORMAL PARTS: article={article} vertices={len(mesh.vertices)} "
                  f"triangles={len(mesh.polygons)} destinations={len(destinations)}")
        print("REVERSED NORMAL PARTS: experimental normals on 5, 20, 13, 28; Blender import interpretation not yet verified.")

    if material_preview:
        # Readable procedural showroom colours, NOT decoded NFS5 textures.
        # Work on imported data only, never alter local source OBJs.
        def showroom_material(name, rgba, metallic=0.0, roughness=0.4,
                              glass=False, rubber=False):
            mat = bpy.data.materials.get("PREVIEW_993_" + name)
            if mat is None:
                mat = bpy.data.materials.new("PREVIEW_993_" + name)
            mat.diffuse_color = rgba
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if bsdf:
                bsdf.inputs["Base Color"].default_value = rgba
                bsdf.inputs["Metallic"].default_value = metallic
                bsdf.inputs["Roughness"].default_value = roughness
                if glass:
                    bsdf.inputs["Transmission Weight"].default_value = 0.22
                    bsdf.inputs["Alpha"].default_value = 0.55
                if rubber:
                    # Generated coordinates; no UV map required.
                    tex = nodes.get("Rubber grain") or nodes.new('ShaderNodeTexNoise')
                    tex.name = "Rubber grain"
                    tex.inputs["Scale"].default_value = 170.0
                    bump = nodes.get("Rubber microtexture") or nodes.new('ShaderNodeBump')
                    bump.name = "Rubber microtexture"
                    bump.inputs["Strength"].default_value = 0.10
                    bump.inputs["Distance"].default_value = 0.008
                    links = mat.node_tree.links
                    links.new(tex.outputs["Fac"], bump.inputs["Height"])
                    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
            if glass:
                if hasattr(mat, 'surface_render_method'):
                    mat.surface_render_method = 'DITHERED'
            return mat

        materials = {
            "paint": showroom_material("Guards_Red_paint", (0.63, 0.018, 0.012, 1), 0.40, 0.23),
            "glass": showroom_material("smoked_glass", (0.045, 0.09, 0.12, 1), 0.05, 0.12, glass=True),
            "rubber": showroom_material("rubber", (0.025, 0.027, 0.030, 1), 0.0, 0.83, rubber=True),
            "trim": showroom_material("black_trim", (0.035, 0.038, 0.044, 1), 0.04, 0.42),
            "silver": showroom_material("alloy", (0.46, 0.49, 0.51, 1), 0.83, 0.27),
            "light": showroom_material("headlight_glass", (0.68, 0.74, 0.79, 1), 0.1, 0.17),
        }
        def category(obj):
            n = (obj.get("crp_name") or obj.name).lower()
            article = obj.get("crp_article")
            if article in (46, 47) or "wheel" in n or "tire" in n or "tyre" in n:
                return "rubber"
            if any(word in n for word in ("glass", "window", "windscreen", "windshield")):
                return "glass"
            if any(word in n for word in ("headlight", "headlamp", "taillight", "tail_light", "brakelight", "lightglass")):
                return "light"
            if any(word in n for word in ("mirror", "grille", "grill", "rubber", "trim", "wiper", "spoiler")):
                return "trim"
            if any(word in n for word in ("rim", "alloy", "brake", "exhaust")):
                return "silver"
            return "paint"

        assigned = {}
        for obj in collection.objects:
            if obj.type != 'MESH':
                continue
            kind = category(obj)
            # Shared mesh datablocks are intentionally assigned one material;
            # this is a coarse whole-object preview, not face-level texturing.
            obj.data.materials.clear()
            obj.data.materials.append(materials[kind])
            obj.color = materials[kind].diffuse_color
            assigned[kind] = assigned.get(kind, 0) + 1
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'
        print("MATERIAL PREVIEW: procedural showroom colours, NOT original NFS5 textures.")
        print("MATERIAL PREVIEW categories:", assigned)
        print("NOTE: procedural wheel rubber is overridden when --original-wheel-textures is enabled.")


    if wheel_texture_paths is not None:
        texture_directory, wheel_obj_directory = wheel_texture_paths
        texture_file = texture_directory / "fs-2-15-whf.png"
        if not texture_file.is_file():
            raise FileNotFoundError(f"Original NFS5 wheel texture missing: {texture_file}")
        input_meshes = {
            46: wheel_obj_directory / "wheel-front-uv.obj",
            47: wheel_obj_directory / "wheel-rear-uv.obj",
        }
        if any(not path.is_file() for path in input_meshes.values()):
            raise FileNotFoundError(f"UV-mapped wheel OBJs missing from {wheel_obj_directory}; run --wheel-uv-mesh for articles 46 and 47")
        for wheel_article, path in input_meshes.items():
            if wheel_article not in wheels:
                raise RuntimeError(f"Wheel article {wheel_article} was not imported into the assembly")
            old_names = set(bpy.data.objects.keys())
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=str(path))
            elif hasattr(bpy.ops.import_scene, "obj"):
                bpy.ops.import_scene.obj(filepath=str(path))
            else:
                raise RuntimeError("OBJ importer unavailable")
            temporary = [obj for obj in bpy.data.objects if obj.name not in old_names and obj.type == 'MESH']
            if len(temporary) != 1 or not temporary[0].data.uv_layers:
                raise RuntimeError(f"UV wheel OBJ must contain one mesh with UV coordinates: {path}")
            original = wheels[wheel_article]
            original_mesh = original.data
            uv_mesh = temporary[0].data
            uv_mesh.name = f"NFS5_{wheel_article}_UV_mapped"
            original.data = uv_mesh
            # The opposite-side TEST_MIRROR was duplicated with shared geometry.
            for candidate in collection.objects:
                if candidate.type == 'MESH' and candidate.data == original_mesh and candidate.get("crp_mirrored_hypothesis"):
                    candidate.data = uv_mesh
            bpy.data.objects.remove(temporary[0], do_unlink=True)
            print(f"ORIGINAL WHEEL TEXTURE: article {wheel_article}: UV mesh {len(uv_mesh.polygons)} triangles, {len(uv_mesh.uv_layers.active.data)} corner UVs")

        texture_material = bpy.data.materials.new("NFS5_original_whf_2x_EXPERIMENT")
        texture_material.use_nodes = True
        nodes = texture_material.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = bpy.data.images.load(str(texture_file.resolve()), check_existing=True)
        image_node.extension = 'CLIP'
        image_node.interpolation = 'Linear'
        uv_node = nodes.new("ShaderNodeUVMap")
        uv_node.uv_map = wheels[46].data.uv_layers.active.name
        transform = nodes.new("ShaderNodeVectorMath")
        transform.operation = 'MULTIPLY_ADD'
        transform.inputs[1].default_value = (2.0, 2.0, 1.0)
        transform.inputs[2].default_value = (0.0, 0.0, 0.0)
        links = texture_material.node_tree.links
        links.new(uv_node.outputs["UV"], transform.inputs[0])
        links.new(transform.outputs["Vector"], image_node.inputs["Vector"])
        links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(image_node.outputs["Alpha"], bsdf.inputs["Alpha"])
        for candidate in collection.objects:
            if candidate.type == 'MESH' and candidate.get("crp_article") in (46, 47):
                candidate.data.materials.clear()
                candidate.data.materials.append(texture_material)
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'
        print("ORIGINAL WHEEL TEXTURES: experimental 2x UV scaling, whf on all four wheels; sidewalls and reverse face not validated.")

    if wheel_alpha_test:
        if wheel_texture_paths is None:
            raise SystemExit("--wheel-alpha-test requires --original-wheel-textures")
        rubber = bpy.data.materials.get("NFS5_WHEEL_RUBBER_ALPHA_TEST")
        if rubber is None:
            rubber = bpy.data.materials.new("NFS5_WHEEL_RUBBER_ALPHA_TEST")
        rubber.diffuse_color = (0.025, 0.027, 0.03, 1.0)
        rubber.use_nodes = True
        rubber_bsdf = rubber.node_tree.nodes.get("Principled BSDF")
        rubber_bsdf.inputs["Base Color"].default_value = rubber.diffuse_color
        rubber_bsdf.inputs["Roughness"].default_value = 0.85

        # Duplicate the original texture shader, but threshold alpha sharply,
        # approximating the source game's transparent wheel billboard.
        clipped = texture_material.copy()
        clipped.name = "NFS5_WHEEL_WHf_ALPHA_CLIP_TEST"
        shader = clipped.node_tree.nodes.get("Principled BSDF")
        tex = next(n for n in clipped.node_tree.nodes if n.type == 'TEX_IMAGE')
        threshold = clipped.node_tree.nodes.new("ShaderNodeMath")
        threshold.operation = 'GREATER_THAN'
        threshold.inputs[1].default_value = 0.45
        clipped.node_tree.links.new(tex.outputs["Alpha"], threshold.inputs[0])
        clipped.node_tree.links.new(threshold.outputs[0], shader.inputs["Alpha"])
        if hasattr(clipped, 'surface_render_method'):
            clipped.surface_render_method = 'DITHERED'
        elif hasattr(clipped, 'blend_method'):
            clipped.blend_method = 'CLIP'
            if hasattr(clipped, 'alpha_threshold'):
                clipped.alpha_threshold = 0.45

        for article in (46, 47):
            wheel = wheels.get(article)
            if wheel is None or len(wheel.data.polygons) != 114:
                raise RuntimeError(f"Expected wheel article {article} with 114 triangles")
            mesh = wheel.data
            mesh.materials.clear()
            mesh.materials.append(rubber)
            mesh.materials.append(clipped)
            for face in mesh.polygons:
                face.material_index = 0 if face.index < 57 else 1
            print(f"WHEEL ALPHA TEST article={article}: group 0x1000 rubber, 0x1001 clipped whf; mirrored side shares mesh")
        print("WHEEL ALPHA TEST: experimental per-group material assignment; no geometry deleted.")

    if wheel_group_diagnostic:
        if wheel_texture_paths is None:
            raise SystemExit("--wheel-group-diagnostic requires --original-wheel-textures")
        # Both first-level rp groups in articles 46/47 have 171 indices,
        # i.e. 57 triangles each. Preserve original face order in the OBJ.
        for article in (46, 47):
            obj = wheels.get(article)
            if obj is None:
                raise RuntimeError(f"Missing wheel article {article}")
            mesh = obj.data
            if len(mesh.polygons) != 114:
                raise RuntimeError(f"Expected 114 first-level wheel triangles, got {len(mesh.polygons)} for {article}")
            meshes = mesh
            meshes.materials.clear()
            for group, color in enumerate(((1.0, 0.08, 0.12, 1.0), (0.02, 0.8, 1.0, 1.0))):
                name = f"NFS5_WHEEL_GROUP_0x100{group}_DEBUG"
                mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
                mat.diffuse_color = color
                mat.use_nodes = True
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                bsdf.inputs["Base Color"].default_value = color
                bsdf.inputs["Alpha"].default_value = 1.0
                mat.use_nodes = True
                meshes.materials.append(mat)
                first, last = group * 57, (group + 1) * 57
                for face in meshes.polygons[first:last]:
                    face.material_index = group
                used = set(i for face in meshes.polygons[first:last] for i in face.vertices)
                coords = [meshes.vertices[i].co for i in used]
                mins = tuple(round(min(v[k] for v in coords), 4) for k in range(3))
                maxs = tuple(round(max(v[k] for v in coords), 4) for k in range(3))
                print(f"WHEEL GROUP DIAGNOSTIC article={article} group=0x100{group} "
                      f"triangles=57 vertices={len(used)} local_min={mins} local_max={maxs}")
        for obj in collection.objects:
            if obj.type == 'MESH' and obj.get("crp_article") not in (46, 47):
                obj.hide_set(True)
                obj.hide_render = True
            if obj.type == 'MESH' and obj.get("crp_article") in (46, 47):
                obj.hide_set(False)
                obj.hide_render = False
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'
                area.spaces.active.overlay.show_relationship_lines = False
                area.spaces.active.overlay.show_extras = False
        print("WHEEL GROUP DIAGNOSTIC: red=0x1000, cyan=0x1001, all other meshes hidden.")

    if wheel_geometry_diagnostic:
        # Keep everything available, but display only the four wheel objects.
        # All other meshes are temporarily hidden for an unambiguous diagnosis.
        wheel_objects = [
            obj for obj in collection.objects
            if obj.type == 'MESH' and obj.get("crp_article") in (46, 47)
        ]
        for obj in collection.objects:
            if obj.type != 'MESH':
                continue
            visible = obj in wheel_objects
            obj.hide_set(not visible)
            obj.hide_render = not visible
        for obj in wheel_objects:
            obj.hide_set(False)
            obj.hide_render = False
            mesh = obj.data
            world_vertices = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
            if world_vertices:
                minimum = tuple(round(min(v[i] for v in world_vertices), 4) for i in range(3))
                maximum = tuple(round(max(v[i] for v in world_vertices), 4) for i in range(3))
            else:
                minimum = maximum = (0, 0, 0)
            material_names = [slot.material.name if slot.material else "<none>" for slot in obj.material_slots]
            print(f"WHEEL DIAGNOSTIC {obj.name}: mirrored={bool(obj.get('crp_mirrored_hypothesis'))} "
                  f"vertices={len(mesh.vertices)} triangles={len(mesh.polygons)} "
                  f"location={tuple(round(n, 4) for n in obj.location)} "
                  f"scale={tuple(round(n, 4) for n in obj.scale)} "
                  f"bounds_min={minimum} bounds_max={maximum} materials={material_names}")
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.overlay.show_relationship_lines = False
                area.spaces.active.overlay.show_extras = False
        print("WHEEL DIAGNOSTIC: all non-wheel meshes hidden in viewport and render; no source OBJ changed.")
        print("In Blender Outliner, toggle individual wheel objects to identify which produces unwanted geometry.")

    if original_headlight_paths is not None:
        png_dir, uv_dir = original_headlight_paths
        source = uv_dir / "article-32-uv.obj"
        image_path = png_dir / "fs-0-23-lit1.png"
        if not source.is_file() or not image_path.is_file():
            raise FileNotFoundError(f"Missing original headlight OBJ or PNG: {source}, {image_path}")
        lights = [o for o in collection.objects if o.type == 'MESH' and o.get("crp_article") == 32]
        if not lights:
            raise RuntimeError("Light1 article 32 is absent from the assembly")
        before = set(bpy.data.objects.keys())
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(source))
        elif hasattr(bpy.ops.import_scene, "obj"):
            bpy.ops.import_scene.obj(filepath=str(source))
        else:
            raise RuntimeError("OBJ importer unavailable")
        temporary = [o for o in bpy.data.objects if o.name not in before and o.type == 'MESH']
        if len(temporary) != 1 or not temporary[0].data.uv_layers:
            raise RuntimeError("Light1 OBJ must contain exactly one UV-mapped mesh")
        mesh = temporary[0].data
        original_mesh = lights[0].data
        if len(mesh.vertices) != len(original_mesh.vertices) or len(mesh.polygons) != len(original_mesh.polygons):
            raise RuntimeError("Light1 UV mesh topology mismatch")
        mesh.name = "NFS5_Light1_lit1_Vflip_EXPERIMENT"
        mat = bpy.data.materials.new("NFS5_Light1_lit1_alpha_test")
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        bsdf.inputs["Roughness"].default_value = 0.30
        uv = nodes.new("ShaderNodeUVMap")
        uv.uv_map = mesh.uv_layers.active.name
        adjust = nodes.new("ShaderNodeVectorMath")
        adjust.operation = 'MULTIPLY_ADD'
        adjust.inputs[1].default_value = (5.9, -5.9, 1.0)
        adjust.inputs[2].default_value = (-3.3832, 2.1586, 0.0)
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = bpy.data.images.load(str(image_path.resolve()), check_existing=True)
        texture.extension = 'CLIP'
        links.new(uv.outputs["UV"], adjust.inputs[0])
        links.new(adjust.outputs["Vector"], texture.inputs["Vector"])
        links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
        threshold = nodes.new("ShaderNodeMath")
        threshold.operation = 'GREATER_THAN'
        threshold.inputs[1].default_value = 0.45
        links.new(texture.outputs["Alpha"], threshold.inputs[0])
        links.new(threshold.outputs[0], bsdf.inputs["Alpha"])
        if hasattr(mat, 'surface_render_method'):
            mat.surface_render_method = 'DITHERED'
        elif hasattr(mat, 'blend_method'):
            mat.blend_method = 'CLIP'
            if hasattr(mat, 'alpha_threshold'):
                mat.alpha_threshold = 0.45
        mesh.materials.clear()
        mesh.materials.append(mat)
        for obj in lights:
            obj.data = mesh
            obj.hide_set(False)
            obj.hide_render = False
        bpy.data.objects.remove(temporary[0], do_unlink=True)
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'
        print(f"ORIGINAL HEADLIGHTS: article=32 instances={len(lights)} "
              f"vertices={len(mesh.vertices)} triangles={len(mesh.polygons)} "
              "UV scale=(5.9,-5.9) offset=(-3.3832,2.1586) alpha=0.45")
        print("ORIGINAL HEADLIGHTS: UV transform and material assignment are experimental.")

    if original_rearlight_paths is not None:
        texture_dir, uv_dir = original_rearlight_paths
        for article, filename in ((17, "fs-0-24-lit2.png"), (18, "fs-0-25-lit3.png")):
            source = uv_dir / f"article-{article}-uv.obj"
            image_path = texture_dir / filename
            if not source.is_file() or not image_path.is_file():
                raise FileNotFoundError(f"Missing light assets: {source}, {image_path}")
            targets = [o for o in collection.objects
                       if o.type == 'MESH' and o.get("crp_article") == article]
            if not targets:
                raise RuntimeError(f"Light article {article} missing from assembly")
            existing = set(bpy.data.objects.keys())
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=str(source))
            elif hasattr(bpy.ops.import_scene, "obj"):
                bpy.ops.import_scene.obj(filepath=str(source))
            else:
                raise RuntimeError("OBJ import unavailable")
            temporary = [o for o in bpy.data.objects if o.name not in existing and o.type == 'MESH']
            if len(temporary) != 1 or not temporary[0].data.uv_layers:
                raise RuntimeError(f"Article {article}: expected one UV-mapped mesh")
            mesh = temporary[0].data
            original_mesh = targets[0].data
            if len(mesh.vertices) != len(original_mesh.vertices) or len(mesh.polygons) != len(original_mesh.polygons):
                raise RuntimeError(f"Article {article}: UV mesh topology mismatch")
            coords = [loop.uv for loop in mesh.uv_layers.active.data]
            min_u = min(v.x for v in coords)
            max_u = max(v.x for v in coords)
            min_v = min(v.y for v in coords)
            max_v = max(v.y for v in coords)
            if max_u - min_u <= 1e-8 or max_v - min_v <= 1e-8:
                raise RuntimeError(f"Article {article}: degenerate UV region")
            su = 1.0 / (max_u - min_u)
            sv = -1.0 / (max_v - min_v)
            du = -min_u * su
            dv = 1.0 - min_v * sv
            mesh.name = f"NFS5_Light_{article}_flipped_autofit_EXPERIMENT"
            mat = bpy.data.materials.new(f"NFS5_Light_{article}_{filename}_alpha_test")
            mat.use_nodes = True
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            bsdf = nodes.get("Principled BSDF")
            bsdf.inputs["Roughness"].default_value = 0.35
            uv_node = nodes.new("ShaderNodeUVMap")
            uv_node.uv_map = mesh.uv_layers.active.name
            mapping = nodes.new("ShaderNodeVectorMath")
            mapping.operation = 'MULTIPLY_ADD'
            mapping.inputs[1].default_value = (su, sv, 1.0)
            mapping.inputs[2].default_value = (du, dv, 0.0)
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(str(image_path.resolve()), check_existing=True)
            tex.extension = 'CLIP'
            links.new(uv_node.outputs["UV"], mapping.inputs[0])
            links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
            links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            clip = nodes.new("ShaderNodeMath")
            clip.operation = 'GREATER_THAN'
            clip.inputs[1].default_value = 0.45
            links.new(tex.outputs["Alpha"], clip.inputs[0])
            links.new(clip.outputs[0], bsdf.inputs["Alpha"])
            if hasattr(mat, 'surface_render_method'):
                mat.surface_render_method = 'DITHERED'
            elif hasattr(mat, 'blend_method'):
                mat.blend_method = 'CLIP'
                if hasattr(mat, 'alpha_threshold'):
                    mat.alpha_threshold = 0.45
            mesh.materials.clear()
            mesh.materials.append(mat)
            for obj in targets:
                obj.data = mesh
                obj.hide_set(False)
                obj.hide_render = False
            bpy.data.objects.remove(temporary[0], do_unlink=True)
            print(f"ORIGINAL REARLIGHTS: article={article} objects={len(targets)} texture={filename} "
                  f"scale=({su:.6f},{sv:.6f}) offset=({du:.6f},{dv:.6f})")
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'
        print("ORIGINAL REARLIGHTS: visually calibrated material/UV mapping; position and original CRP bindings unverified.")

    if glass_light_audit:
        # Read-only geometry/material survey. Existing batch OBJs generally lack
        # UVs; do not pretend the extracted texture can be mapped correctly.
        names = ("glass", "window", "wind", "light", "lamp", "lens",
                 "indicator", "turn", "rear", "roof", "bonnet", "front")
        print("GLASS LIGHT AUDIT: candidate original texture resources:")
        print("  fs-3: glas (64x64), fs-0: lit1/lit2/lit3, fs-1: head")
        print("  Candidates are filenames only: article-material links unverified.")
        found = 0
        for obj in sorted(collection.objects, key=lambda o: o.name):
            if obj.type != 'MESH':
                continue
            name = str(obj.get("crp_name") or obj.name)
            if not any(token in name.lower() for token in names):
                continue
            mesh = obj.data
            mats = [slot.material.name if slot.material else "<none>"
                    for slot in obj.material_slots]
            print(f"GLASS LIGHT AUDIT: article={obj.get('crp_article')} name={name} "
                  f"vertices={len(mesh.vertices)} faces={len(mesh.polygons)} "
                  f"uv_layers={len(mesh.uv_layers)} hidden={obj.hide_get()} "
                  f"materials={mats}")
            found += 1
        print(f"GLASS LIGHT AUDIT: listed {found} candidate objects. "
              "No material assignments changed. No UVs are invented.")

    print(f"NFS5 assembly: imported {imported} articles, missing {missing} files")
    print("Wheels: 46=front, 47=rear; original meshes with exchanged longitudinal CRP positions; mirrored opposite sides (provisional)")
    print("Mesh coordinates unchanged; wheel CRP Z mapped to Blender Y, then axle Y values exchanged.")
    print(f"Wheel longitudinal calibration: +{WHEEL_FORWARD_PREVIEW_OFFSET:.2f} Blender Y (provisional)")
    print("Hinge test empties created for door/bonnet/rear lid; rotate to experiment.")
    print(f"Panel display: {'enabled' if show_panels else 'hidden'} (use --panels to display).")


if __name__ == "__main__":
    main()
