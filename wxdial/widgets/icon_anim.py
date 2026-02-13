# wxdial/widgets/icon_anim.py
import time
import struct
import zlib
import displayio
import gc
import bitmaptools

from .widget import Widget


class WXS2Anim:
    """
    Loads a WXS2 file and can decompress frames one at a time into a single Bitmap.

    Supports BOTH:
      - absolute offsets (offsets point to absolute file positions)
      - relative offsets (offsets are relative to the start of the blob region)

    We auto-detect relative offsets via a simple heuristic.
    """

    def __init__(self, path):
        self.path = path

        self.tile_w = 0
        self.tile_h = 0
        self.frames = 0
        self.colors = 0
        self.palette = None

        self._offsets = None           # list of (off, ln) from file
        self._data_start = 0           # where compressed blobs begin (if relative)
        self._offsets_are_relative = False

        self._f = None
        self.bitmap = None

        self._load_header()

        # One-frame bitmap (NOT the whole sheet)
        self.bitmap = displayio.Bitmap(self.tile_w, self.tile_h, self.colors)

        # Keep file open for speed
        self._f = open(self.path, "rb")

        # Prime with frame 0
        self.load_frame(0)

    def _load_header(self):
        with open(self.path, "rb") as f:
            hdr = f.read(14)
            magic, tw, th, frames, colors, alpha_thr, _ = struct.unpack("<4sHHHHBB", hdr)
            if magic != b"WXS2":
                raise ValueError("Not WXS2")

            self.tile_w = tw
            self.tile_h = th
            self.frames = frames
            self.colors = colors

            pal_bytes = f.read(colors * 3)

            offsets = []
            for _i in range(frames):
                off, ln = struct.unpack("<II", f.read(8))
                offsets.append((off, ln))
            self._offsets = offsets

            # Where the frame blob region begins (useful if offsets are RELATIVE)
            # header(14) + palette(colors*3) + frame_table(frames*8)
            self._data_start = 14 + (colors * 3) + (frames * 8)

        # Heuristic: if any offset is before _data_start, it's almost certainly relative.
        min_off = min(off for off, _ln in self._offsets) if self._offsets else 0
        self._offsets_are_relative = (min_off < self._data_start)

        # Build palette object
        pal = displayio.Palette(self.colors)
        for i in range(self.colors):
            r = pal_bytes[i * 3 + 0]
            g = pal_bytes[i * 3 + 1]
            b = pal_bytes[i * 3 + 2]
            pal[i] = (r << 16) | (g << 8) | b

        pal.make_transparent(0)
        self.palette = pal

    def load_frame(self, n: int):
        n = int(n) % self.frames
        off, ln = self._offsets[n]

        # Convert relative -> absolute if needed
        if self._offsets_are_relative:
            off = self._data_start + off

        # Read this frame's compressed blob
        self._f.seek(off)
        comp = self._f.read(ln)

        # Decompress to exactly tile_w*tile_h bytes
        try:
            raw = zlib.decompress(comp)
        except Exception as e:
            raise ValueError(
                "Bad zlib frame: frame={} off={} ln={} rel={}".format(
                    n, off, ln, self._offsets_are_relative
                )
            ) from e

        # Fast copy into Bitmap (index data)
        # raw must be bytes/bytearray length = tile_w * tile_h
        bitmaptools.arrayblit(self.bitmap, raw, 0, 0, self.tile_w, self.tile_h)

        # Help GC a bit (CircuitPython can be tight)
        comp = None
        raw = None

    def deinit(self):
        if self._f is not None:
            try:
                self._f.close()
            except Exception:
                pass
            self._f = None
        self.bitmap = None
        self.palette = None
        self._offsets = None


class IconAnimWidget(Widget):
    """
    Animated icon widget supporting:
      - .bmp sprite sheets via displayio.OnDiskBitmap (palette transparency index 0)
      - .wxs WXS2 frame-chunked zlib format (one-frame bitmap in RAM)

    If path is None (or ""), displays nothing.

    Params:
      cx, cy: center position
      t: seconds per frame
      path: "/.../name.bmp" or "/.../name.wxs" or None
      tile_w, tile_h: used for BMP tile sizing; WXS2 reads from file
    """

    def __init__(self, *, cx, cy, t, path=None, tile_w=64, tile_h=64, visible=True):
        super().__init__(label=None, value=None, meta=None, visible=visible)

        self.cx = int(cx)
        self.cy = int(cy)
        self.t = float(t)
        self.tile_w = int(tile_w)
        self.tile_h = int(tile_h)

        self.tg = None
        self.path = None

        self._wxs2 = None
        self.frames = 1
        self._frame = 0
        self._next_time = time.monotonic() + self.t

        self.set_path(path, reset=True)

    def _clear(self):
        """Remove any displayed icon and release references."""
        if self.tg is not None:
            try:
                self.remove(self.tg)
            except Exception:
                pass
        self.tg = None

        if self._wxs2 is not None:
            try:
                self._wxs2.deinit()
            except Exception:
                pass
        self._wxs2 = None

        self.frames = 1
        self._frame = 0
        self.path = None

        gc.collect()

    def set_path(self, path, *, reset=True):
        """
        Swap to a new sprite sheet at runtime.

        If path is None (or ""), clears the widget so it displays nothing.
        """
        # Normalize "no icon"
        if path is None or path == "":
            self._clear()
            self._next_time = time.monotonic() + self.t
            return

        # Clear old stuff first (also closes old file handle!)
        self._clear()

        self.path = path
        self._frame = 0

        p = path.lower()
        if p.endswith(".wxs"):
            # WXS2: small RAM footprint, load frames on demand
            self._wxs2 = WXS2Anim(path)
            self.frames = self._wxs2.frames
            tw = self._wxs2.tile_w
            th = self._wxs2.tile_h

            self.tg = displayio.TileGrid(
                self._wxs2.bitmap,
                pixel_shader=self._wxs2.palette,
                width=1,
                height=1,
                tile_width=tw,
                tile_height=th,
            )

            if reset:
                self._wxs2.load_frame(0)

        else:
            # BMP sprite sheet: frames are tiles across X
            bmp = displayio.OnDiskBitmap(path)
            ps = bmp.pixel_shader
            try:
                ps.make_transparent(0)
            except AttributeError:
                pass

            tw = self.tile_w
            th = self.tile_h
            self.frames = max(1, bmp.width // tw)

            self.tg = displayio.TileGrid(
                bmp,
                pixel_shader=ps,
                width=1,
                height=1,
                tile_width=tw,
                tile_height=th,
            )

            if reset:
                self.tg[0] = 0

        # Center it
        if self.tg is not None:
            self.tg.x = self.cx - (tw // 2)
            self.tg.y = self.cy - (th // 2)
            self.append(self.tg)

        self._next_time = time.monotonic() + self.t

    def set_rate(self, t):
        self.t = float(t)
        self._next_time = time.monotonic() + self.t

    def tick(self):
        # Nothing displayed → nothing to animate
        if self.tg is None:
            return False

        now = time.monotonic()
        if now < self._next_time:
            return False

        self._next_time = now + self.t

        if self.frames <= 1:
            return False

        self._frame = (self._frame + 1) % self.frames

        if self._wxs2 is not None:
            self._wxs2.load_frame(self._frame)
        else:
            self.tg[0] = self._frame

        return True
