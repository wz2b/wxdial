# wxdial/wxdial.py

import time
import board
import busio
import digitalio
import random

from wxdial.tempest_decode import TempestUdpDecoder
from wxdial.tempest_event import _WX_LISTENERS, dispatch_wx_event, register_wx

from .wifi_mgr import WifiManager
from wxdial.mockmqtt import MockMQTT
from wxdial.tempest_udp import WxFlowUdp


from .screens.hello import GreetingScreen
from .screens.weather import WeatherScreen
from .screens.wind import WindScreen
from .screens.network import NetworkScreen
from .screens.windrose import WindRoseScreen

from .input import DialInput
from .screens.screen import Screen

from .router import Router
from wxdial import router
from .mockmqtt import MockMQTT
from .dialmqtt import DialMQTT
from .perf import PerfMeter

stats = {}

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

        self.wifimgr = WifiManager()

        

    def run(self):
        last_stats_print = time.monotonic()
        # Display
        self.display = board.DISPLAY
        # self.root = displayio.Group()
        # self.display.root_group = self.root


        # WiFi Manager
        self.wifimgr.startup()

        # UDP listener
        print("Creating UDP listener")
        self.udp = WxFlowUdp(
            pool=self.wifimgr.new_socket_pool(),
            listen_port=50222,
            buffer_size=2048,
            max_packets_per_poll=16,
            decoder=TempestUdpDecoder(altitude_m=0.0, publish_meta=True)
        )
        self.udp.connect()


        # self.mqtt = MockMQTT(emissions)
        # self.mqtt = DialMQTT(broker="ha.autofrog.com",
        #                      port=8883,
        #                      client_id="wxdial",
        #                      wifimgr=self.wifimgr,
        #                      loop_timeout=0.25,      # or 0.01 if 0 is weird
        #                      socket_timeout=0.25,
        #                      stats=stats)
        
        # Touch IRQ
        self.touch_irq = digitalio.DigitalInOut(board.TOUCH_IRQ)
        self.touch_irq.switch_to_input(pull=digitalio.Pull.UP)

        # Input
        self.i2c = busio.I2C(board.SCL, board.SDA, frequency=100_000)
        self.input = DialInput(board.ENC_A, board.ENC_B, board.KNOB_BUTTON, self.i2c, self.touch_irq, invert=True)

        # Router
        self.router = Router()


        # Screens
        rose = WindRoseScreen()
        greeting = GreetingScreen()
        wind = WindScreen()
        weather = WeatherScreen()
        network = NetworkScreen(wifimgr=self.wifimgr)

        screens = [rose, greeting, wind, weather, network]

        # Register screens (or widgets) with router
        # If your @subscribe methods live on the Screen classes, this is enough:
        # from wxdial.tempest_event import register_wx, _WX_LISTENERS

        for s in screens:
            self.router.register(s)
            n=register_wx(s)
            # print("register_wx", type(s).__name__, "->", n)
        # print("TOTAL WX LISTENERS:", len(_WX_LISTENERS))


        # Tell the MQTT boker we're interested in these topics
        # for topic in self.router.topics():
        #     self.mqtt.subscribe(topic)

        # If your @subscribe methods live on widgets owned by each screen,
        # register those widgets here instead (example):
        # for s in screens:
        #     for w in getattr(s, "widgets", []):
        #         self.router.register(w)

        active = screens[0]
        # self.root.append(active)
        self.display.root_group = active
        active.on_show()

        # --- test event timers ---
        next_emit = time.monotonic() + 1.0

        try:
            while True:
                now = time.monotonic()
                current_screen=type(active).__name__

                # Occasionally print tout stats
                if now - last_stats_print >= 10.0:
                    print("--- Performance Stats ---")
                    for k, v in stats.items():
                        print(f"{k}: {v:.3f} sec")
                    print("-------------------------")
                    stats.clear()
                    last_stats_print = now

                with PerfMeter("wifi", stats):
                    self.wifimgr.tick(now)
                
                # with PerfMeter("mqtt", stats):
                #     self.mqtt.poll(now)

                # A) Emit fake weather events occasionally
                # if now >= next_emit:
                #     # speed in mph-ish, dir degrees
                #     spd = random.uniform(0.0, 25.0)
                #     direction = random.randint(0, 359)

                #     # publish to router
                #     self.router.publish("weather/wind_spd", spd)
                #     self.router.publish("weather/wind_dir", direction)

                #     # schedule next emit 0.5 .. 2.0 seconds later
                #     next_emit = now + random.uniform(0.5, 2.0)

                # B) Poll inputs and forward to active screen
                with PerfMeter("input", stats):
                    ev = self.input.poll()
                
                if ev:
                    ev_type, ev_value = ev
                    print("EV:", DialInput.event_name(ev_type), ev_value, "ACTIVE:", type(active).__name__, "IDX:", screens.index(active))
                    

                    with PerfMeter(current_screen + ".input", stats):
                        handled = active.input(*ev)

                    if not handled:
                        if ev_type == DialInput.CW:
                            next_index = (screens.index(active) + 1) % len(screens)

                            active.on_hide()
                            active = screens[next_index]
                            self.display.root_group = active
                            active.on_show()

                        elif ev_type == DialInput.CCW:
                            # print("SWITCH CCW from", type(active).__name__, "to", type(screens[next_index]).__name__)

                            active.on_hide()
                            prev_index = (screens.index(active) - 1) % len(screens)
                            active = screens[prev_index]
                            self.display.root_group = active
                            with PerfMeter(current_screen + ".on_show", stats):
                                active.on_show()

                # C) Tick screen (always)
                with PerfMeter(current_screen + ".tick", stats):
                    active.tick(now)
                
                time.sleep(0.01)

                # D) Handle any routed messages
                # with PerfMeter("mqtt.dispatch", stats):
                #     topics = self.mqtt.drain_dirty()
                #     if topics:
                #         for topic in topics:
                #             self.router.publish(topic, self.mqtt.get(topic))
                
                
                # A) UDP ingest (non-blocking)
                with PerfMeter("wx.poll", stats):
                    events = self.udp.poll()
                with PerfMeter("wx.dispatch", stats):
                    for ev in events:
                        # print("dispatching", ev)
                        called=dispatch_wx_event(ev)
                        print("Successfully dispatched to", called, "listeners")


        finally:
            if self.input:
                self.input.deinit()
            if self.touch_irq:
                self.touch_irq.deinit()
            if self.i2c:
                self.i2c.deinit()
