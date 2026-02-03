# dump_wxs2_table.py
import struct, sys, os

path = sys.argv[1]
sz = os.path.getsize(path)

with open(path, "rb") as f:
    hdr = f.read(14)
    magic, tw, th, frames, colors, alpha_thr, _ = struct.unpack("<4sHHHHBB", hdr)
    print("magic", magic, "tile", tw, th, "frames", frames, "colors", colors, "size", sz)

    f.read(colors * 3)  # palette
    data_start = 14 + (colors * 3) + (frames * 8)
    print("data_start", data_start)

    offs = []
    for i in range(frames):
        b = f.read(8)
        off, ln = struct.unpack("<II", b)
        offs.append((off, ln))

print("first 10 entries:")
for i,(off,ln) in enumerate(offs[:10]):
    print(i, off, ln)

min_off = min(o for o,_ in offs)
max_end_abs = max(o+l for o,l in offs)
print("min_off", min_off, "max_end_abs", max_end_abs)
print("if relative, max_end_rel", data_start + max_end_abs)
