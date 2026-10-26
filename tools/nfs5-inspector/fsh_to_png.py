#!/usr/bin/env python3
"""Convert uncompressed 0x7D FSH/SHPI images to PNG locally.

No external dependencies. Only supports verified 32-bit entries;
does not modify FSH archives or upload extracted game assets.
"""
import argparse
from pathlib import Path
import struct
import zlib


def u32(buf, offset):
    return struct.unpack_from("<I", buf, offset)[0]


def png_rgba(width, height, rgba):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
    raw = b"".join(b"\x00" + rgba[y * width * 4:(y + 1) * width * 4]
                   for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def convert_archive(path, output):
    blob = path.read_bytes()
    if len(blob) < 16 or blob[:4] != b"SHPI":
        raise ValueError(f"{path}: not a SHPI archive")
    size, count = u32(blob, 4), u32(blob, 8)
    if size > len(blob) or size < 16 or count > (size - 16) // 8:
        raise ValueError(f"{path}: invalid archive table")
    written = 0
    for i in range(count):
        at = 16 + i * 8
        name = blob[at:at + 4].decode("latin-1").strip()
        offset = u32(blob, at + 4)
        if offset > size - 16:
            raise ValueError(f"{path}: entry {i} outside archive")
        kind = u32(blob, offset) & 0x7f
        width, height = struct.unpack_from("<HH", blob, offset + 4)
        if kind != 0x7d:
            print(f"Skip {path.name}:{name}: format 0x{kind:02x}")
            continue
        if not (0 < width <= 4096 and 0 < height <= 4096):
            raise ValueError(f"{path}: implausible dimensions for {name}")
        pixel_start = offset + 16
        pixel_count = width * height
        if pixel_count > (size - pixel_start) // 4:
            raise ValueError(f"{path}: truncated pixels for {name}")
        # FSH 0x7D pixels are stored as BGRA in little-endian byte order.
        bgra = blob[pixel_start:pixel_start + pixel_count * 4]
        rgba = bytearray(len(bgra))
        for j in range(0, len(bgra), 4):
            rgba[j:j + 4] = bytes((bgra[j + 2], bgra[j + 1], bgra[j], bgra[j + 3]))
        filename = f"{path.stem}-{i:02}-{name or 'unnamed'}.png"
        dest = output / filename
        if dest.exists():
            raise FileExistsError(f"refusing to overwrite {dest}")
        dest.write_bytes(png_rgba(width, height, rgba))
        print(f"{filename}: {width}x{height}")
        written += 1
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directory containing fs-*.fsh")
    parser.add_argument("destination", type=Path, help="new output directory")
    args = parser.parse_args()
    archives = sorted(args.source.glob("fs-*.fsh"))
    if not archives:
        parser.error("no fs-*.fsh archives found")
    if args.destination.exists():
        parser.error("destination already exists; choose a new directory")
    args.destination.mkdir(parents=True)
    total = sum(convert_archive(p, args.destination) for p in archives)
    print(f"Converted {total} PNG textures into {args.destination}")


if __name__ == "__main__":
    main()
