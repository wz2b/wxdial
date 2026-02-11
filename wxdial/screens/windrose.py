# screens/hello.py

import terminalio
from ..input import DialInput
from .screen import Screen
from ..subscribe import subscribe
from ..tempest_event import subscribewx
from adafruit_display_text import label
from ..widgets import WindRoseWidget, SpiderWebGrid
import random
import math
import json

class WindRoseScreen(Screen):
    def __init__(self):
        super().__init__()

        self.rose = WindRoseWidget(cx=self.cx, cy=self.cy, radius=110,
                                        dir_step_deg=30,
                                        bands=5,
                                        draw_grid=True)
        self.append(self.rose)
    
        # Create a text label
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
            self.rose.clear()
            self.rose.refresh(force=True)
            return True
        
        return False

    
    @subscribe("weather/wind")
    def on_wind(self, payload):
        data = json.loads(payload)
        self.rose.append_sample(
            wind_speed_mph=data['wind_speed_mph'],
            wind_dir_deg=data['wind_dir']
        )

    # @subscribe("weather/gust")
    # def on_gust(self, payload):
    #     data = json.loads(payload)
    #     self.rose.append_sample(
    #         wind_speed_mph=data['wind_speed_avg'],
    #         wind_gust_mph=data['wind_gust_mph'],
    #         wind_dir_deg=data['wind_gust_dir']
    #     )


    @subscribewx()
    def on_weather(self, payload):
        if payload.type == "rapid_wind":
            d = payload.data  # or payload.payload / payload.fields — see below
            self.rose.append_sample(
                wind_speed_mph=d["wind_speed_mph"],
                wind_dir_deg=d["wind_dir_deg"],
            )
        else:
            print("other weather event:", payload.type)


    def tick(self, now):
        self.rose.tick(now)
