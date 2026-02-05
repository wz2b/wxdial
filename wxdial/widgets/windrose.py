# wxdial/widgets/windrose.py

import math
import displayio
import vectorio
from adafruit_display_text import label
import terminalio

from .widget import Widget
from .spider import SpiderWebGrid

print("LOADED wxdial.widgets.windrose (circles + diamond gusts)")


def _norm_deg(d):
    d = d % 360
    if d < 0:
        d += 360
    return d


def _polar(cx, cy, r, ang_rad):
    return (int(cx + r * math.cos(ang_rad)), int(cy + r * math.sin(ang_rad)))


class WindRoseWidget(Widget):
    """
    Wind rose - circle scatter with diamond gusts.
    
    Sustained wind = circles
    Gusts = diamonds
    Speed determines radius from center, direction determines angle.
    """

    def __init__(
        self,
        *,
        cx,
        cy,
        radius=70,
        dir_step_deg=30,
        speed_edges_mph=(0, 5, 10, 15, 20, 25),
        history_len=360,
        blowing_to=True,
        bands=5,
        inner_hole_radius=6,
        draw_grid=True,
    ):
        super().__init__()

        self.cx = int(cx)
        self.cy = int(cy)
        self.radius = int(radius)

        self.speed_edges = tuple(speed_edges_mph)
        self._speed_bins = len(self.speed_edges)
        self.history_len = int(history_len)

        self.blowing_to = bool(blowing_to)
        self.bands = int(bands)
        self.inner_hole_radius = int(inner_hole_radius)

        # --- auto-scaling ---
        self._scale_ranges = [10, 25, 50]  # Available max scales in mph
        self._current_scale_idx = 0  # Start with 10 mph scale
        self._max_observed = 0.0  # Track highest speed seen
        self._scale_change_threshold = 0.8  # Scale up when reaching 80% of current max

        # --- storage ---
        self._samples = []  # list of (dir_deg, speed_mph, shape_obj, is_gust)

        # --- color palette ---
        speed_colors = [
            0xF2E85E,  # yellow
            0xF7B94A,  # orange
            0xE74C3C,  # red
            0x4A90E2,  # blue
            0x2ECC71,  # green
            0x7B1FA2,  # purple
        ]
        
        # Palette: one color per speed bin
        self._palette = displayio.Palette(self._speed_bins)
        for i in range(self._speed_bins):
            self._palette[i] = speed_colors[i % len(speed_colors)]

        # --- layer structure ---
        # Layer 0: Grid (if enabled)
        if draw_grid:
            spoke_angles = list(range(0, 360, int(dir_step_deg)))
            # Use 240x240 for full round display to avoid clipping
            self._grid = SpiderWebGrid(
                cx=cx,
                cy=cy,
                radius=radius,
                inner_radius=inner_hole_radius,
                bands=bands,
                spokes=spoke_angles,
                color=0x404040,
                width=240,  # Full display width
                height=240  # Full display height
            )
            self.append(self._grid)
        else:
            self._grid = None

        # Layer 1: Shapes group (circles and diamonds)
        self._shapes_group = displayio.Group()
        self.append(self._shapes_group)
        


    # ---------- binning ----------

    def _spd_to_bin(self, wind_speed_mph):
        """Map speed to color bin."""
        s = 0.0 if wind_speed_mph is None else float(wind_speed_mph)

        for i in range(len(self.speed_edges) - 1):
            lo = self.speed_edges[i]
            hi = self.speed_edges[i + 1]
            if lo <= s < hi:
                return i

        if s < self.speed_edges[0]:
            return 0
        return len(self.speed_edges) - 1

    def _spd_to_radius(self, wind_speed_mph):
        """Map speed to display radius (distance from center)."""
        s = 0.0 if wind_speed_mph is None else float(wind_speed_mph)
        
        # Use current scale max
        max_speed = self._scale_ranges[self._current_scale_idx]
        
        # Clamp to 0-max_speed range
        s = min(s, max_speed)
        
        # Normalize to 0-1 range
        norm = s / max_speed if max_speed > 0 else 0
        
        # Map to radius range
        r_min = self.inner_hole_radius
        r_max = self.radius
        return int(r_min + (r_max - r_min) * norm)
    
    def _check_scale_adjustment(self, speed):
        """Check if we need to change the scale based on observed speed."""
        if speed is None or speed <= 0:
            return False

        # Update max observed
        if speed > self._max_observed:
            self._max_observed = speed

        current_max = self._scale_ranges[self._current_scale_idx]

        # ---- Scale UP ----
        if speed > current_max * self._scale_change_threshold:
            if self._current_scale_idx < len(self._scale_ranges) - 1:
                self._current_scale_idx += 1
                self._max_observed = speed  # reset tracker for new band

                if self._grid:
                    self._grid.set_scale(max_speed_mph=self._scale_ranges[self._current_scale_idx])

                return True

        # ---- Scale DOWN ----
        # Only consider scaling down if we're not already at the smallest scale.
        if self._current_scale_idx > 0:
            lower_max = self._scale_ranges[self._current_scale_idx - 1]

            # If our observed max is well below what the next-lower scale could show,
            # drop down one notch.
            if self._max_observed < lower_max * 0.6:
                self._current_scale_idx -= 1
                self._max_observed = speed  # reset tracker

                if self._grid:
                    self._grid.set_scale(max_speed_mph=self._scale_ranges[self._current_scale_idx])

                return True

        return False


    # ---------- public API ----------
    def clear(self, reset_scale=True):
        # Swap the entire points layer (fast + forces redraw correctly)
        new_group = displayio.Group()
        self._shapes_group = new_group
        self[1] = new_group          # <-- forces displayio to reconsider that layer

        self._samples = []
        self._max_observed = 0.0

        if reset_scale:
            self._current_scale_idx = 0
            if self._grid:
                self._grid

    def append_sample(self, *, wind_speed_mph=None, wind_dir_deg=None, wind_gust_mph=None):
        """
        Add a wind sample - draws a circle for sustained wind, diamond for gusts.
        
        Args:
            wind_speed_mph: Sustained wind speed (draws circle if provided)
            wind_dir_deg: Wind direction (required)
            wind_gust_mph: Gust speed (draws diamond if provided and >= 5 mph)
        """
        if wind_dir_deg is None:
            return
        
        # Filter out weak gusts (< 5 mph)
        # if wind_gust_mph is not None and wind_gust_mph < 5.0:
        #     wind_gust_mph = None
        
        GUST_MIN_MPH = 5.0
        GUST_DELTA_MPH = 3.0

        is_gust = (
            wind_gust_mph is not None
            and wind_speed_mph is not None
            and wind_gust_mph > GUST_MIN_MPH
            and wind_gust_mph > wind_speed_mph + GUST_DELTA_MPH
        )

        print("speed:", wind_speed_mph, "gust:", wind_gust_mph, "is_gust:", is_gust)

        # Use gust speed if provided, otherwise sustained speed
        speed = wind_gust_mph if is_gust else wind_speed_mph
        
        # Skip if we have no speed data at all
        if speed is None or speed <= 0:
            return
        
        # Check if we need to adjust scale
        scale_changed = self._check_scale_adjustment(speed)

        # Adjust direction if needed
        d = _norm_deg(wind_dir_deg)
        if self.blowing_to:
            d = _norm_deg(d + 180.0)

        # Get position and color
        r = self._spd_to_radius(speed)

        # gusts are always red
        if is_gust:
            color_idx = 2  # your palette index 2 is 0xE74C3C (red)
        else:
            color_idx = self._spd_to_bin(speed)


        # Calculate position (angle starts at North = -90°)
        ang = math.radians(d - 90.0)
        x, y = _polar(self.cx, self.cy, r, ang)

        # Create shape - diamond for gusts, circle for sustained wind
        if is_gust:
            # Diamond: 4-pointed polygon
            size = 5 + int(color_idx * 2 / self._speed_bins)
            points = [
                (0, -size),   # top
                (size, 0),    # right
                (0, size),    # bottom
                (-size, 0),   # left
            ]
            shape = vectorio.Polygon(
                pixel_shader=self._palette,
                points=points,
                x=x-size,
                y=y-size,
                color_index=color_idx
            )
        else:
            # Circle for sustained wind
            circle_radius = 4 + int(color_idx * 2 / self._speed_bins)
            shape = vectorio.Circle(
                pixel_shader=self._palette,
                radius=circle_radius,
                x=x-circle_radius,
                y=y-circle_radius,
                color_index=color_idx
            )
        
        self._shapes_group.append(shape)
        self._samples.append((d, speed, shape, is_gust))

        # If scale changed, need to redraw all existing samples
        if scale_changed:
            self._redraw_all_samples()

        # Maintain history window
        while len(self._samples) > self.history_len:
            old_dir, old_speed, old_shape, old_is_gust = self._samples.pop(0)
            # Remove from group
            for i, obj in enumerate(self._shapes_group):
                if obj is old_shape:
                    self._shapes_group.pop(i)
                    break
    
    def _redraw_all_samples(self):
        """Redraw all samples with new scale - called when scale changes."""
        # Update scale label
        self._scale_label.text = f"{self._scale_ranges[self._current_scale_idx]}"
        
        # Clear shapes
        while len(self._shapes_group):
            self._shapes_group.pop()
        
        # Redraw each sample with new positions
        temp_samples = self._samples[:]
        self._samples = []
        
        for old_dir, old_speed, old_shape, old_is_gust in temp_samples:
            # Recalculate position with new scale
            r = self._spd_to_radius(old_speed)
            color_idx = self._spd_to_bin(old_speed)
            
            ang = math.radians(old_dir - 90.0)
            x, y = _polar(self.cx, self.cy, r, ang)
            
            # Recreate shape
            if old_is_gust:
                size = 5 + int(color_idx * 2 / self._speed_bins)
                points = [(0, -size), (size, 0), (0, size), (-size, 0)]
                shape = vectorio.Polygon(
                    pixel_shader=self._palette,
                    points=points,
                    x=x, y=y,
                    color_index=color_idx
                )
            else:
                circle_radius = 2 + int(color_idx * 2 / self._speed_bins)
                shape = vectorio.Circle(
                    pixel_shader=self._palette,
                    radius=circle_radius,
                    x=x, y=y,
                    color_index=color_idx
                )
            
            self._shapes_group.append(shape)
            self._samples.append((old_dir, old_speed, shape, old_is_gust))
    
    def get_current_scale(self):
        """Return the current max scale in mph."""
        return self._scale_ranges[self._current_scale_idx]

    def tick(self, now=None):
        """Update display - not needed for this simple version."""
        pass