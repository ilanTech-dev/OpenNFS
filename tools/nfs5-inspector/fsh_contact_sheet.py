#!/usr/bin/env python3
"""Generate an annotated contact sheet of locally extracted NFS5 FSH PNGs.

No copyrighted source images are stored in the repository.
Requires Pillow: python3 -m pip install Pillow
Usage: python3 tools/nfs5-inspector/fsh_contact_sheet.py PNG_DIR OUTPUT.png
Optional: --all (include every image, otherwise prioritize lighting/glass/decal names).
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("png_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--all", action="store_true", help="include all FSH-derived images")
    args = parser.parse_args()
    names = ("lit", "head", "glas", "lamp", "brak", "tail", "sign", "fog",
             "rev", "lic", "decal", "wip", "mir", "rear")
    images = sorted(args.png_dir.glob("fs-*.png"))
    if not args.all:
        images = [p for p in images if any(key in p.stem.lower() for key in names)]
    if not images:
        parser.error("No matching fs-*.png images found; try --all")
    columns, tile_w, tile_h = 5, 185, 178
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_w, rows * tile_h), (42, 44, 49))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, path in enumerate(images):
        with Image.open(path) as source:
            img = source.convert("RGBA")
            w, h = img.size
            alpha_extrema = img.getchannel("A").getextrema()
            canvas = Image.new("RGBA", (146, 132), (0, 0, 0, 0))
            thumb = img.copy()
            thumb.thumbnail((142, 128), Image.Resampling.NEAREST)
            canvas.alpha_composite(thumb, ((146-thumb.width)//2, (132-thumb.height)//2))
            # Checker pattern makes real transparency obvious.
            bg = Image.new("RGBA", canvas.size, (190, 190, 190, 255))
            bd = ImageDraw.Draw(bg)
            for y in range(0, 132, 12):
                for x in range(0, 146, 12):
                    if (x//12 + y//12) % 2:
                        bd.rectangle((x, y, x+11, y+11), fill=(115, 115, 115, 255))
            bg.alpha_composite(canvas)
            x, y = (i % columns) * tile_w, (i // columns) * tile_h
            sheet.paste(bg.convert("RGB"), (x+19, y+5))
            draw.text((x+5, y+141), path.name[:29], font=font, fill=(245, 245, 245))
            draw.text((x+5, y+157), f"{w}x{h} alpha={alpha_extrema[0]}..{alpha_extrema[1]}", font=font, fill=(194, 204, 215))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(f"FSH CONTACT SHEET: {len(images)} images -> {args.output}")
    print("NOTE: artwork inspection only; texture-to-geometry assignments remain unverified.")


if __name__ == "__main__":
    main()
