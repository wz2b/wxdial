# screens/hello.py

import terminalio
from ..input import DialInput
from .screen import Screen
from ..subscribe import subscribe
from adafruit_display_text import label
from ..widgets import WindDialWidget, SegmentedWindArrow
import random

class WindScreen(Screen):
    def __init__(self):
        super().__init__()

        self.big_gauge = WindDialWidget(cx=self.cx, cy=self.cy, radius=120)
        self.append(self.big_gauge)
        # # Create a text label
        # text_area = label.Label(
        #     terminalio.FONT,
        #     text="wind",
        #     color=0xFFFFFF,  # White text
        #     anchor_point=(0.5, 0.5),   # center of the label
        #     anchored_position=(self.cx, self.cy),
        # )
        # self.append(text_area)
        self.last_speed = None
        self.last_dir = None
        self.last_gust = None

    def on_show(self):
        pass;

    def on_hide(self):
        pass;

    def input(self, event_type, event_value=None):
        if event_type == DialInput.CLICK:
            speed=random.uniform(0, 25)
            gust=random.uniform(0, 25)
            dir=random.randint(0, 359)
            self.big_gauge.set(
                wind_dir_deg=dir,
                wind_speed_mph=speed,
                wind_gust_mph=gust)         
            return True

    
    @subscribe("weather/wind_spd")  # payload is dict
    def on_wind_speed(self, payload):
        # print("New speed", payload)
        self.last_speed = float(payload)
        self._update_arrow()


    @subscribe("weather/wind_dir")  # payload is dict
    def on_wind_dir(self, payload):
        # print("New direction", payload)
        self.last_dir = float(payload)
        self._update_arrow()

    @subscribe("weather/wind_gust_mph")  # payload is dict
    def on_wind_gust(self, payload):
        # print("New gust", payload)
        self.last_gust = float(payload)
        self._update_arrow()

    def _update_arrow(self):
                self.big_gauge.set(wind_speed_mph=self.last_speed, 
                        wind_dir_deg=self.last_dir,
                        wind_gust_mph=self.last_gust)