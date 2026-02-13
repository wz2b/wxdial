# screens/hello.py  (ObsScreen)

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

class ObsScreen(Screen):
    def __init__(self):
        super().__init__()

        self.big_gauge = WindDialWidget(cx=self.cx, cy=self.cy, radius=120)
        self.append(self.big_gauge)

        temp_font = bitmap_font.load_font("/public/fonts/FreeSansBold24.pcf")
        temp_font.load_glyphs("0123456789-°.FC".encode("utf-8"))
        
        self.temp = TempText(
            x=self.cx,
            y=self.cy,
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

    def _update_arrow(self):
        self.big_gauge.set(
            wind_speed_mph=self.last_speed,
            wind_dir_deg=self.last_dir,
            wind_gust_mph=self.last_gust,
        )

    def tick(self, now):
        # self.temp.tick(now)
        pass
