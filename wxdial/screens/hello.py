# screens/hello.py

from ..input import DialInput
from .screen import Screen
from adafruit_display_text import label
from ..widgets.icon_anim import IconAnimWidget
import time
import os

class GreetingScreen(Screen):
    def __init__(self):
        super().__init__()

        self.icon = IconAnimWidget(
            cx=120,
            cy=120,
            t=0.25,
            path="/wxdial/sprites/na.wxs",
            tile_h=64,
            tile_w=64,
        )

        # for the image rotation test
        self.n = 0

        self.append(self.icon)

        self.sprite_dir = "/wxdial/sprites"
        self.imagelist = [
            self.sprite_dir + "/" + f
            for f in os.listdir(self.sprite_dir)
            if f.lower().endswith(".wxs")
    ]
        self.imagelist.sort()   

    def on_show(self):
        print("GreetingScreen is now shown.")

    def on_hide(self):
        print("GreetingScreen is now hidden.")

    def input(self, event_type, event_value=None):
        if event_type == DialInput.CLICK:
            print("GreetingScreen received a click event.")
            self.n = (self.n + 1) % len(self.imagelist)
            path = self.imagelist[self.n]
            print("Switching to", path)
            self.icon.set_path(path)
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



