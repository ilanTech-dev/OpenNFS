#!/usr/bin/env python3
"""Render original CRP wheel OBJ UV coordinates over a candidate PNG as HTML/SVG.

No additional dependencies. Does not change OBJ or texture assets.
Example:
 python3 tools/nfs5-inspector/wheel_uv_overlay.py \
   ~/gitHub/project-356/wheel-uv/22_WheelFront.obj \
   ~/gitHub/project-356/textures-png/fs-2-08-whf.png \
   ~/gitHub/project-356/uv-wheel-front.html

The left panel shows literal UVs in the [0,1] image square; the right shows
the UV bounding box normalized for visibility. That second view is *diagnostic*,
not an assertion that normalized UVs are the intended game mapping.
"""
import argparse
import base64
import html
import json
import re
import struct
from pathlib import Path


def obj_uv(path):
    uv = []
    triangles = []
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("vt "):
            fields = line.split()
            uv.append((float(fields[1]), float(fields[2])))
        elif line.startswith("f "):
            face = []
            for term in line.split()[1:]:
                fragments = term.split("/")
                if len(fragments) < 2 or not fragments[1]:
                    raise ValueError("Face lacks vt reference")
                idx = int(fragments[1])
                index = idx - 1 if idx > 0 else len(uv) + idx
                if index < 0 or index >= len(uv):
                    raise ValueError(f"Bad vt index: {idx}")
                face.append(index)
            for i in range(1, len(face)-1):
                triangles.append((face[0], face[i], face[i+1]))
    if not uv or not triangles:
        raise ValueError("No UV coordinates or faces found")
    return uv, triangles


def png_dimensions(path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
        raise ValueError("Expected PNG texture")
    return struct.unpack(">II", data[16:24]), data


def svg_paths(uv, faces, transform):
    output = []
    for face in faces:
        pts = []
        for idx in face:
            u, v = uv[idx]
            x, y = transform(u, v)
            pts.append(f"{x:.2f},{y:.2f}")
        output.append('<polygon points="' + ' '.join(pts) + '"/>')
    return '\n'.join(output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("obj", type=Path)
    p.add_argument("png", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    obj, png, output = (v.expanduser().resolve() for v in (args.obj, args.png, args.output))
    uv, faces = obj_uv(obj)
    (w, h), image = png_dimensions(png)
    u0, u1 = min(p[0] for p in uv), max(p[0] for p in uv)
    v0, v1 = min(p[1] for p in uv), max(p[1] for p in uv)
    size = 512
    normalised = lambda u, v: (size*(u-u0)/max(u1-u0, 1e-8),
                               size*(1-(v-v0)/max(v1-v0, 1e-8)))
    literal = lambda u, v: (size*u, size*(1-v))
    raw = svg_paths(uv, faces, literal)
    fitted = svg_paths(uv, faces, normalised)
    encoded = base64.b64encode(image).decode()
    img_uri = "data:image/png;base64,"+encoded
    title = html.escape(obj.name)
    texture = html.escape(png.name)
    report = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>356 wheel UV: {title}</title>
<style>body{{font:15px system-ui;background:#161a1e;color:#f2f2f2;margin:24px}}
main{{display:flex;flex-wrap:wrap;gap:24px}}section{{width:min(512px,100%)}}
svg{{width:100%;height:auto;border:1px solid #747b81;background:#272c32}}
polygon{{stroke:#12f2ae;stroke-width:1;vector-effect:non-scaling-stroke;fill:none}}
small{{color:#b6c1c9}}code{{color:#c6f0e6}}</style>
<h1>CRP wheel UV diagnostic — {title}</h1>
<p>Candidate image: <code>{texture}</code> ({w} × {h} pixels);
{len(uv)} UV vertices, {len(faces)} triangles.</p>
<p>Original UV extents: U <code>[{u0:.6f}, {u1:.6f}]</code>,
V <code>[{v0:.6f}, {v1:.6f}]</code>.
Raw UV span: <code>{u1-u0:.6f} × {v1-v0:.6f}</code>.</p>
<main>
<section><h2>Original UV coordinates</h2>
<small>Literal UV mapping onto the image square, V flipped for SVG display.
Out-of-range UVs are clipped, not wrapped.</small>
<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
<image href="{img_uri}" width="{size}" height="{size}"/>
<g>{raw}</g></svg></section>
<section><h2>UV extents fitted to image (diagnostic only)</h2>
<small>Rescaled to show all UV triangles regardless of original extents;
this is NOT a proposed game texture transform.</small>
<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
<image href="{img_uri}" width="{size}" height="{size}"/>
<g>{fitted}</g></svg></section>
</main>
<p>Compare multiple wheel textures using identical OBJ; the wireframe should
reveal whether the atlas image contains the expected wheel-face geometry.</p>
</html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report)
    print(f"UV OVERLAY: {obj.name}: {len(faces)} triangles, UV U={u0:.4f}..{u1:.4f}, V={v0:.4f}..{v1:.4f}")
    print(f"UV OVERLAY: wrote {output}")


if __name__ == "__main__":
    main()
