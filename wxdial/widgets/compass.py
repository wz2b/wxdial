# widgerts/compass.py
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

import math
import displayio
import vectorio
from adafruit_display_text import label
import terminalio

from .widget import Widget

font = terminalio.FONT


def iround(x):
    return int(round(x))


class CompassRose(Widget):
    def __init__(
        self,
        cx=100,
        cy=100,
        radius=50,
        ring_thickness=2,
        major_tick_len=10,
        minor_tick_len=5,
        major_every_deg=30,
        minor_every_deg=10,
        ring_color=0x404040,
        major_tick_color=0xD0D0D0,
        minor_tick_color=0x707070,
        text_color=0xFFFFFF,
        background_color=0x000000
    ):
        super().__init__()

        self.cx = int(cx)
        self.cy = int(cy)
        self.radius = int(radius)

        # --- ring (fake outline using 2 filled circles) ---
        # Outer circle in ring_color
        outer_pal = displayio.Palette(1)
        outer_pal[0] = ring_color
        outer = vectorio.Circle(
            pixel_shader=outer_pal,
            radius=self.radius,
            x=self.cx,
            y=self.cy,
            color_index=0,
        )
        self.append(outer)


        # Inner circle in background_color to create the "stroke" thickness
        inner_r = max(0, self.radius - int(ring_thickness))
        if inner_r > 0:
            inner_pal = displayio.Palette(1)
            inner_pal[0] = background_color
            inner = vectorio.Circle(
                pixel_shader=inner_pal,
                radius=inner_r,
                x=self.cx,
                y=self.cy,
                color_index=0,
            )
            self.append(inner)

        # --- tick marks ---
        tick_group = displayio.Group()
        self.append(tick_group)

        def add_tick(deg: int, length: int, color: int, half_w: float = 1.5):
            theta = math.radians(deg)

            # Compass mapping: 0° is up
            ux = math.sin(theta)
            uy = -math.cos(theta)

            # Endpoints along the radius (outer to inner)
            x_outer = iround(cx + radius * ux)
            y_outer = iround(cy + radius * uy)
            x_inner = iround(cx + (radius - length) * ux)
            y_inner = iround(cy + (radius - length) * uy)

            # Perpendicular for thickness (px, py) = (-uy, ux)
            px = -uy
            py = ux
            half_w = 1.5   

            ax = iround(x_outer + half_w * px)
            ay = iround(y_outer + half_w * py)
            bx = iround(x_outer - half_w * px)
            by = iround(y_outer - half_w * py)
            ix = x_inner
            iy = y_inner

            pal = displayio.Palette(1)
            pal[0] = color

            tri = vectorio.Polygon(
                pixel_shader=pal,
                points=[(ax, ay), (bx, by), (ix, iy)],
                x=0,
                y=0,
            )
            tick_group.append(tri)

        for deg in range(0, 360, int(minor_every_deg)):
            if deg % int(major_every_deg) == 0:
                add_tick(deg, int(major_tick_len), major_tick_color)
            else:
                add_tick(deg, int(minor_tick_len), minor_tick_color)

        # --- cardinal labels ---
        # place letters slightly inside the ring + inside the major ticks
        label_r = self.radius - int(major_tick_len) - 10

        def add_cardinal(text: str, deg: int):
            theta = math.radians(deg)
            ux = math.sin(theta)
            uy = -math.cos(theta)

            x = self.cx + int(label_r * ux)
            y = self.cy + int(label_r * uy)

            t = label.Label(font, text=text, color=text_color)
            t.anchor_point = (0.5, 0.5)
            t.anchored_position = (x, y)
            self.append(t)

        add_cardinal("N", 0)
        add_cardinal("E", 90)
        add_cardinal("S", 180)
        add_cardinal("W", 270)
