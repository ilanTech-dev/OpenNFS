#!/usr/bin/env python3
"""Find locally installed NFS5 Porsche 356 CRPs and compare their complexity.

This is a read-only scouting tool. Do not commit game files or generated reports.
Usage:
    python3 tools/nfs5-inspector/vehicle_scout.py \
        resources/NFS_5/gamedata/CarModel \
        build/nfs5-inspector/nfs5-inspector \
        ~/gitHub/project-356/scout
Optional --all evaluates every CRP (can take longer). By default inspect
filenames containing 356; if none match, list names and request manual selection.
"""
import argparse
import csv
import re
import subprocess
from pathlib import Path


def inspect(exe, path):
    completed = subprocess.run([str(exe), str(path), "--component-metadata"],
                               text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout)[-1200:])
    output = completed.stdout
    articles = re.search(r"Article count \(header >> 5\): (\d+)", output)
    misc = re.search(r"Misc entries: (\d+)", output)
    descriptors = re.search(r"Article part descriptors: (\d+)", output)
    tags = re.search(r"Part tag frequencies \(raw byte order\):(.*?)(?:Block transitions:|\Z)",
                     output, re.S)
    frequencies = {}
    if tags:
        frequencies = {key: int(value) for key, value in
                       re.findall(r"^\s*(aB|aN|fe|mn|n\$|rp|rt|tv|vu|zd):\s*(\d+)",
                                  tags.group(1), re.M)}
    names = []
    for line in output.splitlines():
        if re.search(r"\b(?:Wheel|Roof|Door|Light|Glass|Cabrio|Bonnet|Hood|Trunk|Body|SunRoof)\b", line, re.I):
            names.append(line)
    return {
        "filename": path.name,
        "articles": articles.group(1) if articles else "?",
        "misc": misc.group(1) if misc else "?",
        "part_descriptors": descriptors.group(1) if descriptors else "?",
        "polygon_descriptors": frequencies.get("rp", "?"),
        "uv_descriptors": frequencies.get("vu", "?"),
        "vertex_descriptors": frequencies.get("tv", "?"),
        "raw_output": output,
        "candidate_lines": names,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("car_model_dir", type=Path)
    p.add_argument("inspector", type=Path)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--all", action="store_true")
    args = p.parse_args()
    car_dir, exe, destination = (x.expanduser().resolve() for x in
                                 (args.car_model_dir, args.inspector, args.output_dir))
    if not car_dir.is_dir() or not exe.is_file():
        p.error("CarModel directory and compiled inspector must exist")
    crps = sorted(car_dir.glob("*.crp"), key=lambda x: x.name.lower())
    if not crps:
        p.error("No .crp files in the CarModel directory")
    candidates = crps if args.all else [file for file in crps if "356" in file.stem]
    if not candidates:
        print("No filename includes 356. Available CRP filenames:")
        for file in crps:
            print(" ", file.name)
        print("Use --all to inspect the complete inventory, or identify the 356 CRP manually.")
        return
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for file in candidates:
        print(f"SCOUT: inspecting {file.name}", flush=True)
        try:
            record = inspect(exe, file)
            (destination / f"{file.stem}-inspector.txt").write_text(record["raw_output"])
            records.append({k: v for k, v in record.items() if k not in ("raw_output", "candidate_lines")})
            print(f"  articles={record['articles']} rp={record['polygon_descriptors']} "
                  f"uv={record['uv_descriptors']} tv={record['vertex_descriptors']}")
        except Exception as exc:
            records.append({"filename": file.name, "error": str(exc)})
            print(f"  ERROR: {exc}")
    columns = ("filename", "articles", "misc", "part_descriptors",
               "polygon_descriptors", "uv_descriptors", "vertex_descriptors", "error")
    with (destination / "vehicle-comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    print(f"SCOUT: comparison saved to {destination / 'vehicle-comparison.csv'}")
    print("SCOUT: source assets unchanged; model identity not inferred from numbers alone.")


if __name__ == "__main__":
    main()
