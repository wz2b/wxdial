import time
import socketpool
import ssl
import adafruit_minimqtt.adafruit_minimqtt as MQTT


class DialMQTT:
    """
    Lightweight MQTT helper for CircuitPython that depends on WifiManager
    for connectivity (no direct SSID/password/wifi.radio.connect usage).

    Behavior:
      - If Wi-Fi is down, MQTT stays idle (won't block / won't spam reconnect).
      - When Wi-Fi comes up, it (re)builds socketpool + MQTT client and connects.
      - Remembers subscriptions and resubscribes on every MQTT reconnect.
      - Keeps last value per topic and a "dirty" set for changed topics.

    Typical use:
        self.mqtt = DialMQTT(wifimgr, broker, port=8883, client_id="wxdial")
        self.mqtt.subscribe("weather/wind_spd")
        ...
        self.mqtt.poll(now)
    """

    # simple internal states
    _IDLE = 0
    _NEED_BUILD = 1
    _CONNECTING = 2
    _CONNECTED = 3

    def __init__(
        self,
        wifimgr,
        broker,
        *,
        port=8883,
        client_id="wxdial",
        keep_alive=60,
        socket_timeout=0.05,
        loop_timeout=0.05,
        reconnect_min_s=1.0,
        reconnect_max_s=30.0,
    ):
        self._wifimgr = wifimgr
        self._broker = broker
        self._port = port
        self._client_id = client_id
        self._keep_alive = keep_alive
        self._socket_timeout = socket_timeout
        self._loop_timeout = loop_timeout

        # backoff / reconnect pacing
        self._reconnect_delay = reconnect_min_s
        self._reconnect_min_s = reconnect_min_s
        self._reconnect_max_s = reconnect_max_s
        self._next_attempt_at = 0.0

        # mqtt objects (built only when wifi is up)
        self._pool = None
        self._ssl = None
        self._client = None

        self._state = self._NEED_BUILD
        self._enabled = True

        # Wi-Fi tracking to detect changes
        self._last_wifi_up = False

        # subscriptions to re-apply after reconnect
        self._subs = set()

        # data store
        self._values = {}   # topic -> last value
        self._dirty = set()

    # ---- MQTT callbacks ----

    def _on_connect(self, client, userdata, flags, rc):
        print("MQTT connected")
        self._state = self._CONNECTED
        self._reconnect_delay = self._reconnect_min_s
        self._next_attempt_at = 0.0

        # Resubscribe everything
        for topic in sorted(self._subs):
            try:
                client.subscribe(topic)
            except Exception as e:
                print("MQTT resubscribe error:", topic, e)

    def _on_disconnect(self, client, userdata, rc):
        print("MQTT disconnected")
        # Don't immediately rebuild here; let poll() decide based on wifi status
        self._state = self._CONNECTING
        self._schedule_reconnect(time.monotonic())

    def _on_message(self, client, topic, payload):
        try:
            msg = payload.decode("utf-8")
        except Exception:
            msg = payload

        self._values[topic] = msg
        self._dirty.add(topic)

    # ---- internal helpers ----

    def _wifi_is_up(self) -> bool:
        # WifiManager reports ssid string when connected
        if self._wifimgr is None:
            return False
        return self._wifimgr.connected_ssid() is not None

    def _schedule_reconnect(self, now: float):
        self._next_attempt_at = now + self._reconnect_delay
        self._reconnect_delay = min(self._reconnect_delay * 2.0, self._reconnect_max_s)

    def _teardown_client(self):
        # Best-effort shutdown
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
        self._client = None
        self._pool = None
        self._ssl = None
        self._state = self._NEED_BUILD

    def _build_client(self):
        """
        Build socketpool + ssl + MQTT client on top of the current WiFi session.

        IMPORTANT:
        SocketPool is tied to the WiFi connection.
        Must be rebuilt after every WiFi reconnect.
        """
        self._pool = self._wifimgr.new_socket_pool()

        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False

        self._client = MQTT.MQTT(
            broker=self._broker,
            port=self._port,
            client_id=self._client_id,
            socket_pool=self._pool,
            ssl_context=self._ssl,
            is_ssl=True,
            keep_alive=self._keep_alive,
            socket_timeout=self._socket_timeout,
        )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._state = self._CONNECTING
        
    def _connect_now(self, now: float):
        if self._client is None:
            self._state = self._NEED_BUILD
            return

        try:
            self._client.connect()
            # on_connect callback will set CONNECTED + resubscribe
        except Exception as e:
            print("MQTT connect error:", e)
            self._state = self._CONNECTING
            self._schedule_reconnect(now)

    # ---- public API ----

    def enable(self, enabled: bool):
        """
        Turn MQTT behavior on/off. When disabled, it tears down the client and goes idle.
        """
        self._enabled = enabled
        if not enabled:
            self._teardown_client()

    def subscribe(self, topic: str):
        """
        Remember subscription and apply immediately if connected.
        """
        if not topic:
            return
        self._subs.add(topic)

        if self._client is not None and self._state == self._CONNECTED:
            try:
                print("Subscribing:", topic)
                self._client.subscribe(topic)
            except Exception as e:
                print("MQTT subscribe error:", e)

    def publish(self, topic, payload):
        if self._client is None or self._state != self._CONNECTED:
            return
        try:
            self._client.publish(topic, payload)
        except Exception as e:
            print("MQTT publish error:", e)
            # publishing error may indicate connection issue; let poll() heal it

    def poll(self, now: float | None = None):
        """
        Call frequently from main loop.

        - If Wi-Fi is down: stay idle (and tear down client if it existed)
        - If Wi-Fi just came up: rebuild client
        - If not connected: attempt connect on backoff schedule
        - If connected: loop() to process incoming messages
        """
        if not self._enabled:
            return

        if now is None:
            now = time.monotonic()

        wifi_up = self._wifi_is_up()

        # Wi-Fi dropped -> tear down MQTT stack so it can rebuild cleanly later
        if not wifi_up:
            if self._last_wifi_up:
                # only print on transition
                print("MQTT: Wi-Fi down; idling")
            self._last_wifi_up = False
            self._teardown_client()
            return

        # Wi-Fi is up
        if not self._last_wifi_up:
            # transition up
            print("MQTT: Wi-Fi up; preparing client")
            self._last_wifi_up = True
            self._teardown_client()     # force clean rebuild on new wifi session
            self._state = self._NEED_BUILD
            self._reconnect_delay = self._reconnect_min_s
            self._next_attempt_at = now

        # Build client if needed
        if self._state == self._NEED_BUILD:
            try:
                self._build_client()
            except Exception as e:
                print("MQTT build error:", e)
                self._schedule_reconnect(now)
                return

        # If not connected, connect on schedule
        if self._state in (self._CONNECTING, self._NEED_BUILD):
            if now >= self._next_attempt_at:
                self._connect_now(now)
            return

        # Connected: process IO
        if self._client is None:
            self._state = self._NEED_BUILD
            return

        try:
            self._client.loop(self._loop_timeout)
        except Exception as e:
            print("MQTT loop error:", e)
            # Force reconnect on next poll, with backoff
            self._state = self._CONNECTING
            self._schedule_reconnect(now)

    def get(self, topic, default=None):
        return self._values.get(topic, default)

    def drain_dirty(self):
        if not self._dirty:
            return None
        topics = set(self._dirty)
        self._dirty.clear()
        return topics
