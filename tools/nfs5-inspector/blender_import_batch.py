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
        raise SystemExit("Usage: blender --python blender_import_batch.py -- <batch-directory> [metadata.csv] [--rear-preset carrera|turbo-s|clubsport] [--lid-type 0|1|2] [--spoiler down|up] [--spoiler-compare] [--animate-spoiler] [--animate-spoiler-smooth] [--lid-underside-compare] [--rear-lid-hinge] [--animate-rear-lid] [--both-doors] [--bonnet-hinge]")
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
    smooth_spoiler = "--animate-spoiler-smooth" in args
    if smooth_spoiler:
        args.remove("--animate-spoiler-smooth")
    animate_spoiler = "--animate-spoiler" in args or smooth_spoiler
    if "--animate-spoiler" in args:
        args.remove("--animate-spoiler")
    if animate_spoiler and rear_preset != "carrera":
        raise SystemExit("--animate-spoiler requires --rear-preset carrera")
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

    print(f"NFS5 assembly: imported {imported} articles, missing {missing} files")
    print("Wheels: 46=front, 47=rear; original meshes with exchanged longitudinal CRP positions; mirrored opposite sides (provisional)")
    print("Mesh coordinates unchanged; wheel CRP Z mapped to Blender Y, then axle Y values exchanged.")
    print(f"Wheel longitudinal calibration: +{WHEEL_FORWARD_PREVIEW_OFFSET:.2f} Blender Y (provisional)")
    print("Hinge test empties created for door/bonnet/rear lid; rotate to experiment.")
    print(f"Panel display: {'enabled' if show_panels else 'hidden'} (use --panels to display).")


if __name__ == "__main__":
    main()
