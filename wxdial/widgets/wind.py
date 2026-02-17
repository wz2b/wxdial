# wxdial/widgets/wind.py
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

import math
import terminalio
import displayio
import vectorio

from adafruit_display_text import label
from .widget import Widget
from .compass import CompassRose
from .arrow import SegmentedWindArrow

_MPH_TO_KTS = 0.868976  # 1 mph = 0.868976 knots


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
        (optional) gust, lull, text
    """

    def __init__(self, *, cx, cy, radius=80, max_mph=50, block_step=5,
                 ring_thickness=2, bg_color=0x000000, **kw):
        super().__init__(**kw)

        self.cx = int(cx)
        self.cy = int(cy)

        # Keep references so we can update later
        self.compass = CompassRose(cx=cx, cy=cy, radius=cx)
        self.append(self.compass)

        self.arrow = SegmentedWindArrow(cx=cx, cy=cy, radius=cx - 10)
        self.append(self.arrow)

        # Optional: initialize hidden / calm
        self.arrow.set(wind_dir_deg=0, wind_speed_kts=0)

    def set(self, value=None, meta=None, *, wind_dir_deg=None, wind_speed_mph=None, wind_gust_mph=None):
        """
        Convenience setter.

        You can call either:
          - set(value=<mph>, meta={"dir": <deg>, "gust": <mph>})
        OR:
          - set(wind_dir_deg=<deg>, wind_speed_mph=<mph>, wind_gust_mph=<mph>)
        """

        # If explicit args are not provided, fall back to Widget-style value/meta
        if wind_speed_mph is None:
            wind_speed_mph = value

        if wind_dir_deg is None and meta:
            wind_dir_deg = meta.get("dir")

        if wind_gust_mph is None and meta:
            # Support a couple common names
            wind_gust_mph = meta.get("gust", meta.get("wind_gust"))

        # Normalize inputs
        try:
            wind_dir_deg = None if wind_dir_deg is None else int(wind_dir_deg) % 360
        except Exception:
            wind_dir_deg = None

        def _to_float_or_none(x):
            if x is None:
                return None
            try:
                return float(x)
            except Exception:
                return None

        wind_speed_mph = _to_float_or_none(wind_speed_mph)
        wind_gust_mph = _to_float_or_none(wind_gust_mph)

        # Convert to knots for SegmentedWindArrow
        wind_speed_kts = None if wind_speed_mph is None else (wind_speed_mph * _MPH_TO_KTS)
        wind_gust_kts = None if wind_gust_mph is None else (wind_gust_mph * _MPH_TO_KTS)

        # If we have no direction, still pass something sane; arrow will hide itself when calm
        if wind_dir_deg is None:
            wind_dir_deg = 0

        # Forward to arrow
        # (If your SegmentedWindArrow doesn't accept wind_gust_kts yet, just remove that argument.)
        self.arrow.set(
            wind_dir_deg=wind_dir_deg,
            wind_speed_kts=wind_speed_kts if wind_speed_kts is not None else 0,
            wind_gust_kts=wind_gust_kts,
        )

        # If your base Widget expects _value/_meta to be maintained, keep them in sync:
        self._value = value
        self._meta = meta
