# wxdial/wxdial.py

import time
import board
import busio
import digitalio
import random

from wxdial.mockmqtt import MockMQTT

from .screens.hello import GreetingScreen
from .screens.weather import WeatherScreen
from .screens.wind import WindScreen

from .input import DialInput
from .screens.screen import Screen

from .router import Router
from wxdial import router
from .mockmqtt import MockMQTT

class WxDial:
    def __init__(self):
        self.display = None
        self.root = None
        self.input = None
        self.i2c = None
        self.touch_irq = None
        self.router = None

        # Create a fake MQTT broker
        emissions = [
            ("weather/wind_spd", 3.0, lambda: random.uniform(0, 25)),
            ("weather/wind_dir", 1.5, lambda: random.randint(0, 359)),
            ("weather/tempF", 5.0, lambda: random.uniform(10, 80)),
            ("garage/door", 10.0, lambda: random.choice(["open", "closed"])),
        ]

        self.mqtt = MockMQTT(emissions)

    def run(self):
        # Display
        self.display = board.DISPLAY
        # self.root = displayio.Group()
        # self.display.root_group = self.root

        self.touch_irq = digitalio.DigitalInOut(board.TOUCH_IRQ)
        self.touch_irq.switch_to_input(pull=digitalio.Pull.UP)

        # Input
        self.i2c = busio.I2C(board.SCL, board.SDA, frequency=100_000)
        self.input = DialInput(board.ENC_A, board.ENC_B, board.KNOB_BUTTON, self.i2c, self.touch_irq)

        # Router
        self.router = Router()

        # Screens
        greeting = GreetingScreen()
        wind = WindScreen()
        weather = WeatherScreen()

        screens = [greeting, wind, weather]

        # Register screens (or widgets) with router
        # If your @subscribe methods live on the Screen classes, this is enough:
        for s in screens:
            self.router.register(s)

        # If your @subscribe methods live on widgets owned by each screen,
        # register those widgets here instead (example):
        # for s in screens:
        #     for w in getattr(s, "widgets", []):
        #         self.router.register(w)

        active = greeting
        # self.root.append(active)
        self.display.root_group = active
        active.on_show()

        # --- test event timers ---
        next_emit = time.monotonic() + 1.0

        try:
            while True:
                now = time.monotonic()

                # A) Emit fake weather events occasionally
                if now >= next_emit:
                    # speed in mph-ish, dir degrees
                    spd = random.uniform(0.0, 25.0)
                    direction = random.randint(0, 359)

                    # publish to router
                    self.router.publish("weather/wind_spd", spd)
                    self.router.publish("weather/wind_dir", direction)

                    # schedule next emit 0.5 .. 2.0 seconds later
                    next_emit = now + random.uniform(0.5, 2.0)

                # B) Poll inputs and forward to active screen
                ev = self.input.poll()
                if ev:
                    active.input(*ev)

                # C) Tick screen
                handled = active.tick(now)
                if not handled:
                    ev_type, ev_value = ev if ev else (None, None)

                    if ev_type == DialInput.CW:
                        active.on_hide()
                        # self.root.remove(active)
                        next_index = (screens.index(active) + 1) % len(screens)
                        active = screens[next_index]
                        # self.root.append(active)
                        self.display.root_group = active
                        active.on_show()

                    elif ev_type == DialInput.CCW:
                        active.on_hide()
                        # self.root.remove(active)
                        prev_index = (screens.index(active) - 1) % len(screens)
                        active = screens[prev_index]
                        # self.root.append(active)
                        self.display.root_group = active
                        active.on_show()
                time.sleep(0.01)

                # D) Handle any routed messages
                topics = self.mqtt.drain_dirty()
                if topics:
                    for topic in topics:
                        router.publish(topic, mqtt.get(topic))


        finally:
            if self.input:
                self.input.deinit()
            if self.touch_irq:
                self.touch_irq.deinit()
            if self.i2c:
                self.i2c.deinit()
