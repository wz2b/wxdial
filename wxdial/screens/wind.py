# screens/hello.py

import terminalio
from ..input import DialInput
from .screen import Screen
from ..subscribe import subscribe
from adafruit_display_text import label
from ..widgets import WindDialWidget, SegmentedWindArrow


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
        

    def on_show(self):
        pass;

    def on_hide(self):
        pass;

    def input(self, event_type, event_value=None):
        return False

    
    @subscribe("weather/wind_spd")  # payload is dict
    def on_wind_speed(self, payload):
        # payload like: {"speed": 12.3, "dir": 270, "maxGust": 22.5}
        # speed = payload.get("speed")
        # self.set(value=speed, meta=payload)
        # do NOT refresh here; let the screen or app refresh per frame
        # print("New speed")
        pass


    @subscribe("weather/wind_dir")  # payload is dict
    def on_wind_dir(self, payload):
        # payload like: {"speed": 12.3, "dir": 270, "maxGust": 22.5}
        # speed = payload.get("speed")
        # self.set(value=speed, meta=payload)
        # do NOT refresh here; let the screen or app refresh per frame
        # print("New direction")
        pass

