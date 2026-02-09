# wxdial/tempest_shim.py
#
# This is a shim that translates from the decoded Tempest packets (topic->value dicts)
# into higher-level WxEvent objects that you can subscribe to with @subscribewx.
# It also tracks some state to synthesize "rapid" events and edge-triggered strike/precip events.
# You can use it like this:
#
#   mqtt = DialMQTT(...)
#   shim = WxMqttShim(mqtt, emit_fn=dispatch_wx_event)
#
#   while True:
#       shim.poll(time.monotonic())
# ...




class WxMqttShim:
    def __init__(self, mqtt, emit_fn, *, obs_period_s=60.0):
        self.mqtt = mqtt              # your DialMQTT
        self.emit = emit_fn           # function(WxEvent)
        self.obs_period_s = obs_period_s

        self.cache = {}               # key -> value (already in mph/F/etc)
        self._next_obs_at = 0.0
        self._strike_count = 0
        self._precip_count = 0

        # subscribe to the topics you care about
        for t in (
            "weather/wind_speed_mph",
            "weather/wind_gust_mph",
            "weather/wind_dir_deg",
            "weather/tempF",
            "weather/rh",
            "weather/pressure_sea_level_inhg",
            # add whatever else you want to synthesize
            "weather/evt/strike",      # optional “trigger” topics
            "weather/evt/precip",
        ):
            self.mqtt.subscribe(t)

    def poll(self, now):
        # drain mqtt changes and update cache
        topics = self.mqtt.drain_dirty()
        if topics:
            for topic in topics:
                self.cache[topic] = self.mqtt.get(topic)

            # if wind changed, emit a rapid packet immediately
            if ("weather/wind_speed_mph" in topics) or ("weather/wind_dir_deg" in topics):
                self._emit_rapid(now)

            # edge-trigger events if present
            if "weather/evt/strike" in topics:
                self._emit_strike(now)
            if "weather/evt/precip" in topics:
                self._emit_precip(now)

        # periodic obs packet
        if now >= self._next_obs_at:
            self._emit_obs(now)
            self._next_obs_at = now + self.obs_period_s

    def _emit_rapid(self, now):
        data = {
            "time_epoch": None,  # can omit or set if you want unix
            "wind_speed_mph": _f(self.cache.get("weather/wind_speed_mph")),
            "wind_dir_deg": _f(self.cache.get("weather/wind_dir_deg")),
        }
        self.emit(WxEvent("rapid", data, ts=now))

    def _emit_obs(self, now):
        data = {
            "wind_speed_mph": _f(self.cache.get("weather/wind_speed_mph")),
            "wind_gust_mph": _f(self.cache.get("weather/wind_gust_mph")),
            "wind_dir_deg": _f(self.cache.get("weather/wind_dir_deg")),
            "tempF": _f(self.cache.get("weather/tempF")),
            "rh": _f(self.cache.get("weather/rh")),
            "pressure_sea_level_inhg": _f(self.cache.get("weather/pressure_sea_level_inhg")),
        }
        self.emit(WxEvent("obs", data, ts=now))

    def _emit_strike(self, now):
        # you can put a payload on the mqtt trigger if you want distance/energy
        self._strike_count += 1
        data = {
            "time": now,
            "distance_mi": None,
            "energy": None,
            "count": self._strike_count,
        }
        self.emit(WxEvent("evt_strike", data, ts=now))

    def _emit_precip(self, now):
        self._precip_count += 1
        data = {
            "time": now,
            "rain_began": now,
            "count": self._precip_count,
        }
        self.emit(WxEvent("evt_precip", data, ts=now))


def _f(x):
    try:
        return float(x)
    except Exception:
        return None
