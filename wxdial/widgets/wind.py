# wxdial/widgets/wind.py

import math
import terminalio
import displayio
import vectorio

from adafruit_display_text import label
from .widget import Widget
from .compass import CompassRose
from .arrow import SegmentedWindArrow

def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


class WindDialWidget(Widget):
    """
    Big wind dial:
      - arrow points to direction (degrees)
      - speed shown as blocks in 5-mph increments
      - optional numeric readout

    Data:
      value: speed (int mph)
      meta:
        dir: int degrees (0..359)
        (optional) text, gust, lull
    """

    def __init__(self, *, cx, cy, radius=80, max_mph=50, block_step=5, 
                 ring_thickness=2, bg_color=0x000000, **kw):
        super().__init__(**kw)


        self.append(CompassRose(cx=cx, cy=cy, radius=cx))

        arrow = SegmentedWindArrow(cx=cx, cy=cy, radius=cx-10)

        arrow.set(wind_dir_deg=450, wind_speed_kts=17)
        self.append(arrow)


        # self.cx = cx
        # self.cy = cy
        # self.radius = radius
        # self.ring_thickness = ring_thickness
        # self.bg_color = bg_color
        # self.max_mph = max_mph
        # self.block_step = block_step
        # # --- palettes ---
        # ring_pal = displayio.Palette(1)
        # ring_pal[0] = 0xE0E0E0   # soft white like your photo (tweak)

        # bg_pal = displayio.Palette(1)
        # bg_pal[0] = bg_color

        # # --- OUTER ring (filled) ---
        # self._outer = vectorio.Circle(
        #     pixel_shader=ring_pal,
        #     x=cx,
        #     y=cy,
        #     radius=radius,
        #     color_index=0,
        # )
        # self.append(self._outer)

        # # --- INNER "cutout" (filled with background) ---
        # inner_r = radius - ring_thickness
        # self._inner_cutout = vectorio.Circle(
        #     pixel_shader=bg_pal,
        #     x=cx,
        #     y=cy,
        #     radius=inner_r,
        #     color_index=0,
        # )
        # self.append(self._inner_cutout)



        # # Arrow (triangle). We'll update its points on refresh().
        # arrow_palette = displayio.Palette(1)
        # arrow_palette[0] = 0xFFFFFF
        # self._arrow_palette = arrow_palette

        # # Placeholder triangle; points replaced in _render()
        # self.arrow = vectorio.Polygon(
        #     pixel_shader=arrow_palette,
        #     points=[(0, 0), (0, 0), (0, 0)],
        #     x=0,
        #     y=0,
        #     color_index=0,
        # )
        # self.append(self.arrow)

        # # Numeric readout
        # self.readout = label.Label(
        #     terminalio.FONT,
        #     text="-- mph",
        #     color=0xFFFFFF,
        #     anchor_point=(0.5, 0.5),
        #     anchored_position=(cx, cy),
        # )
        # self.append(self.readout)

        # # Speed blocks (rectangles). Arrange along bottom or around ring later.
        # # For v1: horizontal strip under dial.
        # self._blocks = []
        # self._block_palette = displayio.Palette(1)
        # self._block_palette[0] = 0x00A0FF  # you can theme later

        # self._block_count = self.max_mph // self.block_step  # e.g. 50/5=10 blocks
        # block_w = 10
        # block_h = 10
        # gap = 4

        # total_w = self._block_count * block_w + (self._block_count - 1) * gap
        # start_x = cx - total_w // 2
        # y = cy + radius + 14  # under dial

        # for i in range(self._block_count):
        #     x = start_x + i * (block_w + gap)
        #     r = vectorio.Rectangle(
        #         pixel_shader=self._block_palette,
        #         x=x,
        #         y=y,
        #         width=block_w,
        #         height=block_h,
        #         color_index=0,
        #     )
        #     # We'll show/hide blocks by toggling r.hidden
        #     r.hidden = True
        #     self._blocks.append(r)
        #     self.append(r)

        # # Cache last rendered
        # self._last_dir = None
        # self._last_speed = None

    # ---- geometry helpers ----

    def _set_arrow(self, deg):
        """
        Update triangle points to point at deg (0 = north/up).
        We'll draw triangle in absolute coords.
        """
        # Convert degrees to radians (0°=up). math uses 0 rad = +x.
        # Make 0° point up: angle = (deg - 90) degrees in math coords.
        a = math.radians(deg - 90)

        # Arrow shape: tip at ~radius, base closer to center
        tip_r = self.radius - 6
        base_r = self.radius * 0.45
        half_w = 10  # half width of base

        # Tip point
        tip_x = self.cx + int(math.cos(a) * tip_r)
        tip_y = self.cy + int(math.sin(a) * tip_r)

        # Base center
        base_x = self.cx + int(math.cos(a) * base_r)
        base_y = self.cy + int(math.sin(a) * base_r)

        # Perpendicular vector for base width
        px = -math.sin(a)
        py = math.cos(a)

        left_x = base_x + int(px * half_w)
        left_y = base_y + int(py * half_w)

        right_x = base_x - int(px * half_w)
        right_y = base_y - int(py * half_w)

        # vectorio.Polygon uses points relative to (x,y) offset.
        # We'll use absolute coordinates by setting x=y=0.
        self.arrow.x = 0
        self.arrow.y = 0
        self.arrow.points = [(tip_x, tip_y), (left_x, left_y), (right_x, right_y)]

    def _set_blocks(self, speed_mph):
        speed_mph = 0 if speed_mph is None else int(speed_mph)
        speed_mph = _clamp(speed_mph, 0, self.max_mph)

        lit = speed_mph // self.block_step
        for i, r in enumerate(self._blocks):
            r.hidden = (i >= lit)

    # ---- rendering ----

    def _render(self, dirty_flags):
        # Extract data
        speed = self._value
        meta = self._meta or {}
        deg = meta.get("dir")

        # Normalize
        if speed is not None:
            try:
                speed = int(speed)
            except Exception:
                speed = None

        if deg is not None:
            try:
                deg = int(deg) % 360
            except Exception:
                deg = None

        # Arrow update
        if deg is None:
            # If unknown, hide arrow
            self.arrow.hidden = True
        else:
            self.arrow.hidden = False
            if deg != self._last_dir:
                self._set_arrow(deg)
                self._last_dir = deg

        # Speed update
        if speed is None:
            self.readout.text = "-- mph"
            self._set_blocks(0)
        else:
            if speed != self._last_speed:
                self.readout.text = "{} mph".format(speed)
                self._set_blocks(speed)
                self._last_speed = speed
