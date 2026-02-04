import math
import vectorio
import displayio
from .widget import Widget


class SegmentedWindArrow(Widget):
    """
    Wind direction indicator that lives on a ring and points outward,
    with stem blocks that light up as wind speed increases.

    Optional gust blocks are rendered as white-outline / black-fill blocks
    for the additional blocks above base wind speed.
    """

    def __init__(self, cx=120, cy=120, radius=120):
        super().__init__()

        self.cx = int(cx)
        self.cy = int(cy)
        self.radius = int(radius)

        # --- colors ---
        self.block_off_color = 0x303030   # dark gray, visible but quiet
        self.block_colors = [0x00FF00, 0xFFFF00, 0xFF8000, 0xFF0000]

        # Gust style (outline)
        self.gust_outline_color = 0xFFFFFF
        self.gust_fill_color = 0x000000   # black interior (matches your wipe/background)

        # We'll "hide" by moving off-screen
        self._hide_x = -200
        self._hide_y = -200

        # --- wipe mask (black) behind arrow to cover compass letters ---
        self.wipe_pal = displayio.Palette(1)
        self.wipe_pal[0] = 0x000000

        self.wipe_local = [
            (-10, -18),
            ( 10, -18),
            ( 10,  38),
            (-10,  38),
        ]

        self.wipe = vectorio.Polygon(
            pixel_shader=self.wipe_pal,
            points=[(0, 0)] * 4,
            x=self._hide_x,
            y=self._hide_y,
        )
        self.append(self.wipe)

        # Arrowhead polygon (local coords; points "up" in local space)
        self.head_pal = displayio.Palette(1)
        self.head_pal[0] = 0xFFFFFF

        self.head_local = [(0, -14), (6, -2), (-6, -2)]
        self.head = vectorio.Polygon(
            pixel_shader=self.head_pal,
            points=[(0, 0)] * len(self.head_local),
            x=self._hide_x,
            y=self._hide_y,
        )
        self.append(self.head)

        # Stem blocks (4 rectangles), defined in LOCAL coords, rotated each update
        self.blocks = []        # list[(poly, pal)]
        self.blocks_local = []  # list[list[(x,y)]]

        # Gust blocks: two polys per block (outer outline + inner fill)
        self.gust_blocks = []        # list[(outer_poly, outer_pal, inner_poly, inner_pal)]
        self.gust_blocks_local = []  # list[(outer_pts, inner_pts)]

        block_w = 4
        block_h = 6
        gap = 2

        # For “outlined” look: outer is normal size, inner is inset by 1 px
        inset = 1

        for i in range(4):
            # --- base block ---
            pal = displayio.Palette(1)
            pal[0] = self.block_off_color

            y_top = -2 + i * (block_h + gap)

            local = [
                (-block_w, y_top),
                ( block_w, y_top),
                ( block_w, y_top + block_h),
                (-block_w, y_top + block_h),
            ]

            poly = vectorio.Polygon(
                pixel_shader=pal,
                points=[(0, 0)] * 4,
                x=self._hide_x,
                y=self._hide_y,
            )

            self.blocks_local.append(local)
            self.blocks.append((poly, pal))
            self.append(poly)

            # --- gust “outline” block (outer + inner) ---
            outer_pal = displayio.Palette(1)
            outer_pal[0] = self.gust_outline_color

            inner_pal = displayio.Palette(1)
            inner_pal[0] = self.gust_fill_color

            outer_pts = local

            # inset rectangle (shrink on all sides)
            inner_pts = [
                (-block_w + inset, y_top + inset),
                ( block_w - inset, y_top + inset),
                ( block_w - inset, y_top + block_h - inset),
                (-block_w + inset, y_top + block_h - inset),
            ]

            outer_poly = vectorio.Polygon(
                pixel_shader=outer_pal,
                points=[(0, 0)] * 4,
                x=self._hide_x,
                y=self._hide_y,
            )
            inner_poly = vectorio.Polygon(
                pixel_shader=inner_pal,
                points=[(0, 0)] * 4,
                x=self._hide_x,
                y=self._hide_y,
            )

            # IMPORTANT: append gust polys AFTER the wipe (done) but BEFORE? AFTER base blocks?
            # If you want gust overlay to sit ON TOP of base blocks, append them after base poly.
            self.gust_blocks_local.append((outer_pts, inner_pts))
            self.gust_blocks.append((outer_poly, outer_pal, inner_poly, inner_pal))
            self.append(outer_poly)
            self.append(inner_poly)

        # initial
        self.set(wind_dir_deg=0, wind_speed_kts=0, wind_gust_kts=None)

    # ---- helpers ----

    def _rotate_points(self, pts, c, s):
        out = []
        for x, y in pts:
            out.append((int(x * c - y * s), int(x * s + y * c)))
        return out

    def _speed_to_blocks(self, kts):
        if kts is None:
            return 0
        kts = float(kts)
        if kts < 1:
            return 0
        elif kts < 5:
            return 1
        elif kts < 10:
            return 2
        elif kts < 15:
            return 3
        else:
            return 4

    def _hide(self):
        self.wipe.x = self._hide_x
        self.wipe.y = self._hide_y

        self.head.x = self._hide_x
        self.head.y = self._hide_y

        for poly, pal in self.blocks:
            poly.x = self._hide_x
            poly.y = self._hide_y
            pal[0] = self.block_off_color

        for outer_poly, outer_pal, inner_poly, inner_pal in self.gust_blocks:
            outer_poly.x = self._hide_x
            outer_poly.y = self._hide_y
            inner_poly.x = self._hide_x
            inner_poly.y = self._hide_y
            # pal colors can stay as-is; position hides them

    # ---- public API ----

    def set(self, wind_dir_deg, wind_speed_kts, wind_gust_kts=None):
        """
        wind_dir_deg: meteorological degrees (0=N, 90=E, 180=S, 270=W)
        wind_speed_kts: knots (base / sustained)
        wind_gust_kts: knots (optional gust)
        """

        # Calm: hide arrow (direction meaningless)
        if wind_speed_kts is None or float(wind_speed_kts) < 1:
            self._hide()
            return

        theta = math.radians(wind_dir_deg)
        ux = math.sin(theta)
        uy = -math.cos(theta)

        px = int(self.cx + self.radius * ux)
        py = int(self.cy + self.radius * uy)

        ang = math.atan2(uy, ux) + (math.pi / 2.0)
        c = math.cos(ang)
        s = math.sin(ang)

        # Wipe
        self.wipe.x = px
        self.wipe.y = py
        self.wipe.points = self._rotate_points(self.wipe_local, c, s)

        # Head
        self.head.x = px
        self.head.y = py
        self.head.points = self._rotate_points(self.head_local, c, s)

        # Base blocks
        for i, (poly, pal) in enumerate(self.blocks):
            poly.x = px
            poly.y = py
            poly.points = self._rotate_points(self.blocks_local[i], c, s)

        # Gust blocks (outer + inner)
        for i, (outer_poly, outer_pal, inner_poly, inner_pal) in enumerate(self.gust_blocks):
            outer_pts, inner_pts = self.gust_blocks_local[i]
            outer_poly.x = px
            outer_poly.y = py
            outer_poly.points = self._rotate_points(outer_pts, c, s)

            inner_poly.x = px
            inner_poly.y = py
            inner_poly.points = self._rotate_points(inner_pts, c, s)

        # Compute how many blocks to show
        n_base = self._speed_to_blocks(wind_speed_kts)
        n_gust = self._speed_to_blocks(wind_gust_kts)

        # Light base blocks
        for i, (_, pal) in enumerate(self.blocks):
            pal[0] = self.block_colors[i] if i < n_base else self.block_off_color

        # Show gust “extra” blocks only above base
        # Hide gust blocks by moving them offscreen when not used (fast + simple)
        for i, (outer_poly, outer_pal, inner_poly, inner_pal) in enumerate(self.gust_blocks):
            if i >= n_base and i < n_gust:
                # keep positioned (already set above)
                pass
            else:
                outer_poly.x = self._hide_x
                outer_poly.y = self._hide_y
                inner_poly.x = self._hide_x
                inner_poly.y = self._hide_y
