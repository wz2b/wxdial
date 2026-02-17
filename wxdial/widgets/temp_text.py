# wxdial/widgets/temp_text.py
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

import terminalio
from adafruit_display_text import label

from .widget import Widget


class TempText(Widget):
    """
    Temperature display widget.

    - value: numeric temperature (float/int) or None
    - meta:
        {
            "unit": "F" or "C",        # default "F"
            "auto_color": True/False   # default True
        }

    Renders a single centered temperature label.
    """

    def __init__(
        self,
        *,
        x,
        y,
        font=None,
        unit="F",
        auto_color=True,
        visible=True,
    ):
        super().__init__(value=None, meta={"unit": unit, "auto_color": auto_color}, visible=visible)

        self._font = font if font is not None else terminalio.FONT

        # Create label
        self._label_obj = label.Label(
            self._font,
            text="--°" + unit,
            color=0xFFFFFF,
            anchor_point=(0.5, 0.5),
            anchored_position=(x, y),
        )

        self.append(self._label_obj)

    # ---- formatting ----

    def format_value(self):
        v = self._value
        unit = self._meta.get("unit", "F")

        if v is None:
            return f"--°{unit}"

        try:
            return f"{int(round(v))}°{unit}"
        except Exception:
            return f"{v}°{unit}"

    # ---- rendering ----

    def _render(self, dirty_flags):
        # Update text if value or meta changed
        if dirty_flags & (self.DIRTY_VALUE | self.DIRTY_META):
            self._label_obj.text = self.format_value()

            if self._meta.get("auto_color", True):
                self._label_obj.color = self._temp_color(self._value)

    # ---- color logic ----

    def _temp_color(self, t):
        """
        Basic stepped temperature color mapping.
        Modify later if you want smoother gradients.
        """
        if t is None:
            return 0x808080  # gray

        try:
            t = float(t)
        except Exception:
            return 0xFFFFFF

        # Fahrenheit thresholds (adjust later if supporting C)
        if t <= 32:
            return 0x4A90E2  # blue
        elif t <= 60:
            return 0x2ECC71  # green
        elif t <= 80:
            return 0xF7B94A  # orange
        else:
            return 0xE74C3C  # red
