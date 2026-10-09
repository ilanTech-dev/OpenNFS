"""Import local NFS5 OBJ batch into Blender, keeping all pieces separately selectable.

In Blender's Scripting workspace:
    exec(compile(open("/home/YOU/gitHub/OpenNFS/tools/nfs5-inspector/blender_import_batch.py").read(), "...", "exec"))

Prefer instead:
    blender --python tools/nfs5-inspector/blender_import_batch.py -- /tmp/project-porsche/batch-v2

Import only generated assets from your own game installation. Never commit/export game assets.
"""
import bpy
import csv
import sys
from pathlib import Path

def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args:
        raise SystemExit("Usage: blender --python blender_import_batch.py -- /path/to/batch-v2")
    batch = Path(args[0]).expanduser()
    manifest = batch / "manifest.csv"
    if not manifest.is_file():
        raise SystemExit(f"No manifest found: {manifest}")
    collection = bpy.data.collections.new("NFS5 Porsche 993 - components")
    bpy.context.scene.collection.children.link(collection)
    # Only show a minimal body assembly by default; alternate/animated parts
    # remain imported but hidden until inspected one at a time.
    initially_visible = {5, 13, 20, 28, 36, 46, 47, 48, 49}
    imported = 0
    missing = 0
    with manifest.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["status"] != "exported":
                continue
            index = int(row["article"])
            file = batch / row["file_or_reason"]
            if not file.is_file():
                missing += 1
                continue
            before = set(bpy.data.objects.keys())
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=str(file))
            elif hasattr(bpy.ops.import_scene, "obj"):
                bpy.ops.import_scene.obj(filepath=str(file))
            else:
                raise RuntimeError("Blender OBJ importer unavailable")
            objects = [obj for obj in bpy.data.objects if obj.name not in before]
            for obj in objects:
                obj.name = f"{index:03d}_{row['name']}"
                for old in list(obj.users_collection):
                    old.objects.unlink(obj)
                collection.objects.link(obj)
                obj.hide_set(index not in initially_visible)
                obj.hide_render = index not in initially_visible
                obj["crp_article"] = index
                obj["crp_name"] = row["name"]
            imported += 1
    print(f"NFS5 assembly: imported {imported} articles, missing {missing} files")
    print("Use Outliner to reveal hidden components; no transforms have been applied.")

if __name__ == "__main__":
    main()
