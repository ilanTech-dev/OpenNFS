"""Import local NFS5 OBJ articles with component metadata and experimental wheel placement.

Generate assembly-metadata.csv via nfs5-inspector --assembly-metadata first.
Run:
  blender --python tools/nfs5-inspector/blender_import_batch.py -- ~/gitHub/project-porsche/batch
Original game resources stay local and must not be committed.
"""
import bpy
import csv
import sys
from pathlib import Path


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args:
        raise SystemExit("Usage: blender --python blender_import_batch.py -- <batch-directory> [metadata.csv]")
    batch = Path(args[0]).expanduser()
    manifest = batch / "manifest.csv"
    metadata = Path(args[1]).expanduser() if len(args) > 1 else batch / "assembly-metadata.csv"
    if not manifest.is_file() or not metadata.is_file():
        raise SystemExit("Missing manifest.csv or assembly-metadata.csv; run --assembly-metadata first")
    with metadata.open(newline="") as stream:
        meta = {int(row["article"]): row for row in csv.DictReader(stream)}

    collection = bpy.data.collections.new("NFS5 Porsche 993 - components")
    bpy.context.scene.collection.children.link(collection)
    # CRP is Y-up, while Blender uses Z-up. One root transform rotates
    # both mesh vertices and CRP component translations consistently.
    root = bpy.data.objects.new("Porsche_993_CRP_to_Blender", None)
    collection.objects.link(root)
    root.rotation_euler = (0.0, 0.0, 0.0)
    root["coordinate_conversion"] = "mesh unchanged; translation (x,y,z) -> (x,z,y)"
    initially_visible = {5, 20}  # hide movable panels for alignment
    # The TypeIndex=1 wheel meshes are variants, not left/right positions.
    # Opposite-side mirroring is an unverified reconstruction hypothesis.
    wheels = {}
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
                visible = index in initially_visible or index in (46, 47)
                obj.hide_set(not visible)
                obj.hide_render = not visible
                if index in (46, 47) and info and int(info["has_transform"]):
                    obj.location = (float(info["tx"]), float(info["tz"]), float(info["ty"]))
                    wheels[index] = obj
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

    print(f"NFS5 assembly: imported {imported} articles, missing {missing} files")
    print("Wheels: 46/47 at CRP translations, opposite sides mirrored (UNVERIFIED)")
    print("Mesh coordinates unchanged; wheel translation Y/Z swapped.")
    print("Door/hood pivots preserved as properties; movable panels hidden.")


if __name__ == "__main__":
    main()
