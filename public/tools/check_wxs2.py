#!/usr/bin/env python3
import struct
import zlib
from pathlib import Path
import sys

def check(path: Path):
    data = path.read_bytes()
    size = len(data)
    if size < 14:
        raise SystemExit("File too small")

    magic, tw, th, frames, colors, alpha_thr, _ = struct.unpack_from("<4sHHHHBB", data, 0)
    print("file:", path)
    print("size:", size, "bytes")
    print("magic:", magic)
    print("tile:", tw, "x", th, "frames:", frames, "colors:", colors, "alpha_thr:", alpha_thr)

    if magic != b"WXS2":
        raise SystemExit("Not WXS2 (magic mismatch)")

    header_len = 14
    pal_len = colors * 3
    table_len = frames * 8
    data_start = header_len + pal_len + table_len
    print("data_start:", data_start)

    if size < data_start:
        raise SystemExit("Truncated: file smaller than header+palette+table")

    # Read offsets table
    offsets = []
    p = header_len + pal_len
    for i in range(frames):
        off, ln = struct.unpack_from("<II", data, p + i * 8)
        offsets.append((off, ln))

    min_off = min(off for off, _ in offsets) if offsets else 0
    max_end = max(off + ln for off, ln in offsets) if offsets else 0
    print("min_off:", min_off, "max_end:", max_end)

    # Heuristic: offsets might be relative to data_start
    rel = (min_off < data_start)
    print("offsets_relative?:", rel)

    # Bounds check + zlib check each frame
    want = tw * th
    for i, (off, ln) in enumerate(offsets):
        abs_off = data_start + off if rel else off
        end = abs_off + ln
        if abs_off < 0 or end > size:
            raise SystemExit(f"Frame {i}: out of bounds off={abs_off} ln={ln} end={end} size={size}")

        comp = data[abs_off:end]
        try:
            raw = zlib.decompress(comp)
        except Exception as e:
            print(f"Frame {i}: zlib FAIL off={abs_off} ln={ln} first8={comp[:8].hex()}")
            raise

        if len(raw) != want:
            raise SystemExit(f"Frame {i}: bad raw size {len(raw)} expected {want}")

    print("OK: all frames decompress and sizes match")
    print()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_wxs2.py file.wxs")

    check(Path(sys.argv[1]))
