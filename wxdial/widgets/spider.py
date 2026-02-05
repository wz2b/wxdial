# wxdial/widgets/spider.py

import math
import displayio
import bitmaptools
from adafruit_display_text import label
import terminalio


def _polar(cx, cy, r, ang_rad):
    return (int(cx + r * math.cos(ang_rad)), int(cy + r * math.sin(ang_rad)))


class SpiderWebGrid(displayio.Group):
    """
    Bitmap-backed spiderweb grid.

    - Draws rings/spokes into a 1-bit bitmap (fast).
    - Optionally draws ring labels as vector text overlays.
    - Supports live scale changes via set_scale().
    """

    def __init__(
        self,
        *,
        cx,
        cy,
        radius,
        inner_radius=0,

        # Geometry knob: how many radial bands (outer ring included)
        bands=5,

        # Meaning knob: what the OUTER ring represents
        max_speed_mph=10,

        spokes=(0, 90, 180, 270),  # degrees
        color=0x404040,

        # Label options
        draw_labels=True,
        label_color=0xFFFFFF,
        label_angle_deg=135,   # where labels sit (deg, 0=N,90=E). 135 = lower-left-ish
        label_inset_px=2,      # move labels slightly inward from ring
        label_min_ring_px=12,  # don't label tiny inner rings

        width=None,
        height=None,
    ):
        super().__init__()

        self.cx = int(cx)
        self.cy = int(cy)
        self.radius = int(radius)
        self.inner_radius = int(inner_radius)

        self.bands = max(1, int(bands))
        self.max_speed_mph = float(max_speed_mph)

        self.spokes = tuple(spokes)
        self.color = int(color) & 0xFFFFFF

        self.draw_labels = bool(draw_labels)
        self.label_color = int(label_color) & 0xFFFFFF
        self.label_angle_deg = float(label_angle_deg)
        self.label_inset_px = int(label_inset_px)
        self.label_min_ring_px = int(label_min_ring_px)

        # Bitmap size
        self.width = int(width) if width is not None else int(2 * radius)
        self.height = int(height) if height is not None else int(2 * radius)

        # 2-color palette: 0=transparent, 1=grid color
        self._palette = displayio.Palette(2)
        self._palette[0] = 0x000000
        self._palette[1] = self.color
        self._palette.make_transparent(0)

        # Bitmap and tilegrid (layer 0)
        self._bitmap = displayio.Bitmap(self.width, self.height, 2)
        self._tilegrid = displayio.TileGrid(
            self._bitmap,
            pixel_shader=self._palette,
            x=0,
            y=0,
        )
        self.append(self._tilegrid)

        # Labels group (layer 1) - kept separate so rebuild() can nuke/regen it
        self._labels = displayio.Group()
        self.append(self._labels)

        self.rebuild()

    # ---------- public controls ----------

    def set_color(self, rgb):
        self.color = int(rgb) & 0xFFFFFF
        self._palette[1] = self.color

    def set_scale(self, *, max_speed_mph=None, bands=None):
        """
        Update the meaning/geometry and redraw.

        - max_speed_mph: outer ring value (10/25/50 etc)
        - bands: number of radial bands (outer ring included)
        """
        changed = False

        if max_speed_mph is not None:
            v = float(max_speed_mph)
            if v > 0 and v != self.max_speed_mph:
                self.max_speed_mph = v
                changed = True

        if bands is not None:
            b = max(1, int(bands))
            if b != self.bands:
                self.bands = b
                changed = True

        if changed:
            self.rebuild()

    def rebuild(self):
        """Clear and redraw bitmap + labels."""
        bitmaptools.fill_region(self._bitmap, 0, 0, self.width, self.height, 0)
        while len(self._labels):
            self._labels.pop()

        self._draw_grid()

        if self.draw_labels:
            self._draw_ring_labels()

    # ---------- drawing ----------

    def _draw_grid(self):
        # Rings: 1..bands inclusive (includes outer ring)
        for i in range(1, self.bands + 1):
            r = int(self.radius * i / self.bands)
            if r <= self.inner_radius:
                continue
            self._draw_circle(self.cx, self.cy, r)

        # Spokes
        for deg in self.spokes:
            ang = math.radians(deg - 90.0)  # -90 so 0° is up
            x0, y0 = _polar(self.cx, self.cy, self.inner_radius, ang)
            x1, y1 = _polar(self.cx, self.cy, self.radius, ang)
            self._draw_line(x0, y0, x1, y1)

    def _draw_ring_labels(self):
        """
        Label each ring with its mph value.
        Ring i corresponds to (i/bands) * max_speed_mph.
        """
        ang = math.radians(self.label_angle_deg - 90.0)

        for i in range(1, self.bands + 1):
            r = int(self.radius * i / self.bands)
            if r <= self.inner_radius + self.label_min_ring_px:
                continue

            mph = (self.max_speed_mph * i) / self.bands

            # nice formatting: integers as "10", non-integers as "2.5"
            if abs(mph - round(mph)) < 1e-6:
                txt = str(int(round(mph)))
            else:
                txt = f"{mph:.1f}"

            rr = max(self.inner_radius, r - self.label_inset_px)
            x, y = _polar(self.cx, self.cy, rr, ang)

            lab = label.Label(
                terminalio.FONT,
                text=txt,
                color=self.label_color,
                background_color=None,
                x=x,
                y=y,
                anchor_point=(0.5, 0.5),
                background_tight=True,
            )
            self._labels.append(lab)

    def _draw_circle(self, cx, cy, r, segments=48):
        prev_x, prev_y = None, None
        for i in range(segments + 1):
            ang = 2.0 * math.pi * i / segments
            x, y = _polar(cx, cy, r, ang)
            if prev_x is not None:
                self._draw_line(prev_x, prev_y, x, y)
            prev_x, prev_y = x, y

    def _draw_line(self, x0, y0, x1, y1):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)

        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        while True:
            if 0 <= x0 < self.width and 0 <= y0 < self.height:
                self._bitmap[x0, y0] = 1

            if x0 == x1 and y0 == y1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
