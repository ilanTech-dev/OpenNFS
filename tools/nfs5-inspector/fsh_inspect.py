#!/usr/bin/env python3
"""Read-only directory inspector for FSH/SHPI texture archives extracted from NFS5 CRP.

No third-party packages. Does not decode or distribute game artwork.
"""
import argparse
from pathlib import Path
import struct


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def inspect(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 16 or data[:4] != b"SHPI":
        raise ValueError(f"{path}: missing SHPI header")
    declared, count = u32(data, 4), u32(data, 8)
    if declared < 16 or declared > len(data) or count > (declared - 16) // 8:
        raise ValueError(f"{path}: invalid archive length or directory")
    print(f"{path.name}: declared={declared} actual={len(data)} entries={count}"
          f" group={data[12:16]!r}")
    directory = []
    for i in range(count):
        pos = 16 + i * 8
        name = data[pos:pos + 4].decode("latin-1")
        offset = u32(data, pos + 4)
        directory.append((name, offset))
    for i, (name, offset) in enumerate(directory):
        if offset > declared - 16:
            print(f"  [{i:02}] {name!r} offset={offset} INVALID")
            continue
        # Image record headers generally begin with a packed type/length word,
        # followed by unsigned 16-bit width and height. These are candidates
        # until we validate against actual supported image payloads.
        word = u32(data, offset)
        format_code = word & 0x7F
        length_field = word >> 8
        width, height = u16(data, offset + 4), u16(data, offset + 6)
        next_offset = min((other for _, other in directory if other > offset),
                          default=declared)
        print(f"  [{i:02}] {name!r} offset={offset:>7} "
              f"code=0x{format_code:02x} flags=0x{word & 0xff:02x} "
              f"recordLengthField={length_field} dimensions={width}x{height} "
              f"bytesUntilNext={next_offset - offset}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path,
                        help="Directory containing locally extracted fs-*.fsh files")
    args = parser.parse_args()
    files = sorted(args.directory.glob("fs-*.fsh"))
    if not files:
        parser.error("no fs-*.fsh files found")
    for path in files:
        inspect(path)


if __name__ == "__main__":
    main()
