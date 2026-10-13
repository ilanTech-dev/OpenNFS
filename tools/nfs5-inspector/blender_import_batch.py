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
from pathlib import Path


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args:
        raise SystemExit("Usage: blender --python blender_import_batch.py -- <batch-directory> [metadata.csv] [--panels | --door-test | --door-closed | --door-hinge | --both-doors]")
    both_doors = "--both-doors" in args
    door_hinge = "--door-hinge" in args or both_doors
    door_closed = "--door-closed" in args
    door_test = "--door-test" in args
    show_panels = "--panels" in args
    args = [item for item in args if item not in ("--panels", "--door-test", "--door-closed", "--door-hinge", "--both-doors")]
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
                if index in PANEL_ARTICLES and info and int(info["has_transform"]):
                    panels.setdefault(index, []).append(obj)
            imported += 1

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

    print(f"NFS5 assembly: imported {imported} articles, missing {missing} files")
    print("Wheels: 46/47 at CRP translations, opposite sides mirrored (UNVERIFIED)")
    print("Mesh coordinates unchanged; wheel translation Y/Z swapped.")
    print(f"Wheel longitudinal calibration: +{WHEEL_FORWARD_PREVIEW_OFFSET:.2f} Blender Y (provisional)")
    print("Hinge test empties created for door/bonnet/rear lid; rotate to experiment.")
    print(f"Panel display: {'enabled' if show_panels else 'hidden'} (use --panels to display).")


if __name__ == "__main__":
    main()
