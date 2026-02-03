# screens/hello.py

from ..input import DialInput
from .screen import Screen
from adafruit_display_text import label
from ..widgets.wx_icon import WxIcon
import time
import os

class GreetingScreen(Screen):
    def __init__(self):
        super().__init__()

        self.icon = WxIcon(
            cx=120,
            cy=120,
            t=0.150,
            icon_path="/wxdial/sprites",
            tile_h=120,
            tile_w=120,
        )

        # for the image rotation test
        self.n = 0

        self.append(self.icon)


    def on_show(self):
        print("GreetingScreen is now shown.")

    def on_hide(self):
        print("GreetingScreen is now hidden.")

    def input(self, event_type, event_value=None):
        if event_type == DialInput.CLICK:
            # print("GreetingScreen received a click event.")
            self.n = (self.n + 1) % 48
            self.icon.set_code(self.n)
            return True
        elif event_type == DialInput.CW:
            print("GreetingScreen received a clockwise rotation.")
            return False
        elif event_type == DialInput.CCW:
            print("GreetingScreen received a counter-clockwise rotation.")
            return False
        elif event_type == DialInput.TAP:
            x, y = event_value
            print(f"TAP at ({x}, {y})")
            return False
        else:
            event_name = DialInput.event_name(event_type)
            # print(event_name, event_value)
            return False
    
    def tick(self, now):
        # Animate current sprite
        self.icon.animate()



