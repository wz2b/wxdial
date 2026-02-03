from PIL import Image, ImageSequence
from pathlib import Path
import argparse
import struct
import zlib


def _rgba_sheet_to_indexed(sheet_rgba, *, colors=16, alpha_threshold=10):
    """
    Convert RGBA sheet to palettized indices where index 0 is reserved for transparency.
    Returns: (indexed_P_image, palette_rgb_triplets_bytes)

    Guarantees:
      - returned image mode 'P'
      - returned pal_bytes length == colors*3
      - palette index 0 is (0,0,0) placeholder for transparency
      - indices 1..colors-1 map to visible colors (padded if fewer)
    """
    if colors < 2 or colors > 256:
        raise ValueError("colors must be 2..256")

    visible_colors = colors - 1

    # Quantize visible pixels to at most (colors-1) colors
    rgb = sheet_rgba.convert("RGB")
    vis_p = rgb.quantize(colors=visible_colors, method=Image.MEDIANCUT)

    # Opaque mask from alpha
    alpha = sheet_rgba.getchannel("A")
    opaque_mask = alpha.point(lambda a: 255 if a > alpha_threshold else 0)

    # Shift visible indices by +1 so 0 stays transparent
    vis_shifted = vis_p.point(lambda i: i + 1)

    # Output indexed image (all transparent initially)
    out = Image.new("P", sheet_rgba.size, color=0)
    out.paste(vis_shifted, mask=opaque_mask)

    # ---- Build a fixed-length palette ----
    # vis_p.getpalette() may be shorter than expected; normalize it.
    vis_pal = vis_p.getpalette() or []
    # We want exactly visible_colors*3 bytes. Pad with zeros if short.
    need = visible_colors * 3
    if len(vis_pal) < need:
        vis_pal = list(vis_pal) + [0] * (need - len(vis_pal))
    else:
        vis_pal = list(vis_pal[:need])

    # index 0 = transparent placeholder, indices 1.. = visible palette
    pal_bytes = bytes([0, 0, 0] + vis_pal)  # length should be colors*3

    # PIL wants a full 768-byte palette attached to the image for saving/viewing,
    # but our file only stores colors*3 bytes.
    full_pal = list(pal_bytes) + [0] * (768 - len(pal_bytes))
    out.putpalette(full_pal)

    # Safety check
    if len(pal_bytes) != colors * 3:
        raise ValueError(f"internal error: pal_bytes len {len(pal_bytes)} expected {colors*3}")

    return out, pal_bytes



def gif_to_sprite_wxs2(
    gif_path,
    out_path,
    size=(64, 64),
    colors=16,
    every_n=1,
    max_frames=32,
    alpha_threshold=10,
    zlib_level=9,
):
    """
    Convert GIF to WXS2:
      - palettized indices with index 0 reserved for transparency
      - palette stored (colors entries)
      - EACH FRAME stored as its own zlib-compressed blob
      - file contains an offset+length table for random access
    """
    gif_path = Path(gif_path)
    out_path = Path(out_path)

    im = Image.open(gif_path)

    frames = []
    for idx, fr in enumerate(ImageSequence.Iterator(im)):
        if idx % every_n != 0:
            continue
        fr = fr.convert("RGBA").resize(size, Image.LANCZOS)
        frames.append(fr)
        if len(frames) >= max_frames:
            break

    if not frames:
        raise ValueError(f"No frames extracted from {gif_path}")

    tile_w, tile_h = map(int, size)
    nframes = len(frames)

    # Build RGBA sheet (frames across X) so palette sees all frames
    sheet_rgba = Image.new("RGBA", (tile_w * nframes, tile_h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet_rgba.paste(f, (i * tile_w, 0))

    # Convert to indexed + palette
    sheet_p, pal_bytes = _rgba_sheet_to_indexed(
        sheet_rgba, colors=colors, alpha_threshold=alpha_threshold
    )

    # CRITICAL: palette in file must be colors*3 bytes (NOT 768)
    if len(pal_bytes) != colors * 3:
        raise ValueError(
            f"pal_bytes wrong length: {len(pal_bytes)} (expected {colors*3}). "
            "You are probably writing a full 768-byte palette."
        )
    
    # Repack to frame-major raw bytes: [frame0][frame1]...
    pix = sheet_p.tobytes()  # sheet row-major
    row_stride = tile_w * nframes
    frame_bytes = tile_w * tile_h

    raw_frames = []
    for f in range(nframes):
        buf = bytearray(frame_bytes)
        dst = 0
        for y in range(tile_h):
            src = y * row_stride + f * tile_w
            buf[dst : dst + tile_w] = pix[src : src + tile_w]
            dst += tile_w
        raw_frames.append(bytes(buf))

    # Compress each frame separately
    comp_frames = [zlib.compress(rf, level=zlib_level) for rf in raw_frames]

    # ---- Write WXS2 ----
    # Header:
    #   magic 'WXS2'
    #   tile_w u16, tile_h u16
    #   frames u16
    #   colors u16
    #   alpha_threshold u8
    #   reserved u8
    #
    # Then:
    #   palette: colors*3 bytes
    #   frame table: frames * (offset u32, length u32)  offsets from file start
    #   frame data blobs: concatenated

    out_path.parent.mkdir(parents=True, exist_ok=True)

    header = struct.pack(
            "<4sHHHHBB",
            b"WXS2",
            tile_w,
            tile_h,
            nframes,
            colors,
            alpha_threshold & 0xFF,
            0,
        )

    table_entry_size = 8
    table_size = nframes * table_entry_size

    with open(out_path, "wb") as f:
        # 1) Header + palette
        f.write(header)
        f.write(pal_bytes)  # colors*3 bytes

        # 2) Reserve table space (we'll backfill later)
        table_pos = f.tell()
        f.write(b"\x00" * table_size)

        # 3) Write each compressed frame, recording ABSOLUTE offsets
        offsets = []
        for cf in comp_frames:
            off = f.tell()              # absolute offset in file
            f.write(cf)
            offsets.append((off, len(cf)))

        # 4) Backfill the table
        end_pos = f.tell()
        f.seek(table_pos)
        for off, ln in offsets:
            f.write(struct.pack("<II", off, ln))
        f.seek(end_pos)



    # Print summary
    total_raw = nframes * frame_bytes
    total_comp = sum(len(x) for x in comp_frames)
    kb = out_path.stat().st_size / 1024
    ratio = (total_comp / total_raw) if total_raw else 0.0

    print(
        f"{gif_path.name:20s} -> {out_path.name:20s}  "
        f"frames={nframes:2d}  tile={tile_w}x{tile_h}  colors={colors:3d}  "
        f"raw={total_raw/1024:6.1f}KB  zlib={total_comp/1024:6.1f}KB  file={kb:6.1f}KB  ratio={ratio:5.2f}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert GIF animations to WXS2 (frame-chunked zlib) files (.wxs)")
    parser.add_argument("input_dir", type=Path, help="Directory to scan recursively for .gif files")
    parser.add_argument("-o", "--out", type=Path, default=Path("out"), help="Output root directory (default: ./out)")
    parser.add_argument("--size", type=int, nargs=2, default=(64, 64))
    parser.add_argument("--colors", type=int, default=16)
    parser.add_argument("--every-n", type=int, default=1)
    parser.add_argument("--max-frames", type=int, default=32)
    parser.add_argument("--alpha-threshold", type=int, default=10)
    parser.add_argument("--zlib-level", type=int, default=9)

    args = parser.parse_args()

    in_root = args.input_dir.resolve()
    out_root = args.out.resolve()

    if not in_root.is_dir():
        raise SystemExit(f"Not a directory: {in_root}")

    gifs = list(in_root.rglob("*.gif"))
    if not gifs:
        raise SystemExit(f"No .gif files found under {in_root}")

    for gif in gifs:
        rel = gif.relative_to(in_root)
        out_path = (out_root / rel).with_suffix(".wxs")

        gif_to_sprite_wxs2(
            gif_path=gif,
            out_path=out_path,
            size=tuple(args.size),
            colors=args.colors,
            every_n=args.every_n,
            max_frames=args.max_frames,
            alpha_threshold=args.alpha_threshold,
            zlib_level=args.zlib_level,
        )
