import wifi
import socketpool
import ssl
import adafruit_minimqtt.adafruit_minimqtt as MQTT


class DialMQTT:
    """
    Lightweight MQTT helper for CircuitPython.

    - Keeps last value per topic
    - Tracks which topics changed since last drain
    - Does NOT own application logic
    """

    def __init__(
        self,
        ssid,
        password,
        broker,
        *,
        port=8883,
        client_id="wxdial",
        keep_alive=60,
    ):
        # --- WiFi ---
        self._wifi = wifi.radio
        if not self._wifi.connected:
            print("Connecting WiFi...")
            self._wifi.connect(ssid, password)
            print("WiFi connected")

        # --- MQTT ---
        self._pool = socketpool.SocketPool(self._wifi)
        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False

        self._client = MQTT.MQTT(
            broker=broker,
            port=port,
            client_id=client_id,
            socket_pool=self._pool,
            ssl_context=self._ssl,
            is_ssl=True,
            keep_alive=keep_alive,
            socket_timeout=0.05,
        )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        # --- data store ---
        self._values = {}        # topic -> last value
        self._dirty = set()      # topics updated since last drain

    # ---- MQTT callbacks ----

    def _on_connect(self, client, userdata, flags, rc):
        print("MQTT connected")

    def _on_disconnect(self, client, userdata, rc):
        print("MQTT disconnected")

    def _on_message(self, client, topic, payload):
        # Decode payload defensively
        try:
            msg = payload.decode("utf-8")
        except Exception:
            msg = payload  # leave as bytes if decode fails

        self._values[topic] = msg
        self._dirty.add(topic)

    # ---- public API ----

    def connect(self):
        self._client.connect()

    def disconnect(self):
        self._client.disconnect()

    def subscribe(self, topic):
        print("Subscribing:", topic)
        self._client.subscribe(topic)

    def publish(self, topic, payload):
        self._client.publish(topic, payload)

    def poll(self):
        """
        Call frequently from main loop.
        """
        try:
            self._client.loop(0.05)
        except Exception as e:
            # keep app alive even if broker flakes
            print("MQTT loop error:", e)

    def get(self, topic, default=None):
        """
        Get last value for a topic.
        """
        return self._values.get(topic, default)

    def drain_dirty(self):
        """
        Return set of topics updated since last call,
        then clear the dirty set.
        """
        if not self._dirty:
            return None

        topics = set(self._dirty)
        self._dirty.clear()
        return topics

