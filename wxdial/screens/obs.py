# screens/hello.py  (ObsScreen)
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

import terminalio
from adafruit_display_text import label
from displayio import Group

from ..input import DialInput
from .screen import Screen
from ..tempest_event import subscribewx
from ..widgets import WindDialWidget
from ..widgets import TempText
import random
from adafruit_bitmap_font import bitmap_font
from ..widgets.wx_icon import WxIcon


class ObsScreen(Screen):
    def __init__(self):
        super().__init__()

        self.big_gauge = WindDialWidget(cx=self.cx, cy=self.cy, radius=120)
        self.append(self.big_gauge)

        temp_font = bitmap_font.load_font("/public/fonts/FreeSansBold24.pcf")
        temp_font.load_glyphs("0123456789-°.FC".encode("utf-8"))
        
        self.icon = WxIcon(
            cx=self.cx,
            cy=self.cy - 53,
            t=0.150,
            code=44,
            tile_h=120,
            tile_w=120,
        )
        self.append(self.icon)

        self.temp = TempText(
            x=self.cx,
            y=self.cy + 5,
            font=temp_font,
        )
        self.append(self.temp)
        
        # --- waiting overlay (top layer) ---
        self._has_obs = False
        self._waiting_layer = self._build_waiting_layer()
        self.append(self._waiting_layer)  # append last => topmost

        self.last_speed = None
        self.last_dir = None
        self.last_gust = None

    def _build_waiting_layer(self):
        g = Group()

        text_nodata = label.Label(
            terminalio.FONT,
            text="No data yet",
            color=0xFFFFFF,
            anchor_point=(0.5, 0.5),
            anchored_position=(self.cx, self.cy + 50),
        )
        g.append(text_nodata)
        return g

    def on_show(self):
        # Show overlay until we have seen at least one obs_st
        self._waiting_layer.hidden = self._has_obs

    def on_hide(self):
        pass

    def input(self, event_type, event_value=None):
        return False

    @subscribewx()
    def on_weather(self, payload):
        if payload.type == "obs_st":
            # First real data => hide waiting overlay
            if not self._has_obs:
                self._has_obs = True
                self._waiting_layer.hidden = True

            self.last_speed = payload.wind_speed_mph
            self.last_dir = payload.wind_dir_deg
            self.last_gust = payload.wind_gust_mph


            self.temp.set(value=payload.temp_f)
            print("Temp dirty:", self.temp._dirty)
            self._update_arrow()
        elif payload.type == "custom":
            icon = getattr(payload, "wxicon", None)
            if icon is not None:
                try:
                    self.icon.set_code(icon)
                except Exception as e:
                    print(f"!!!! Error setting icon: {e}")

    def _update_arrow(self):
        self.big_gauge.set(
            wind_speed_mph=self.last_speed,
            wind_dir_deg=self.last_dir,
            wind_gust_mph=self.last_gust,
        )

    def tick(self, now):
        # Animate current sprite
        self.icon.tick(now)
