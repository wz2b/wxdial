import time

class MockMQTT:
    """
    DialMQTT-compatible mock.

    - poll(): generates updates into an internal cache
    - get(topic): fetch last value for a topic
    - drain_dirty(): returns topics updated since last drain
    - subscribe(topic): optional filter; records interest (supports exact topics)
    """

    def __init__(self, emissions, *, start_immediately=True):
        """
        emissions: list of (topic, interval_sec, producer)

          topic: str
          interval_sec: float seconds between emits
          producer: constant OR callable() -> value

        start_immediately: if True, first emit happens on first poll()
        """
        self._items = []
        self._values = {}      # topic -> last value
        self._dirty = set()    # topics changed since last drain
        self._subs = set()     # subscribed topics (optional gating)

        now = time.monotonic()
        for topic, interval, producer in emissions:
            interval = float(interval)
            nxt = now if start_immediately else (now + interval)
            self._items.append({
                "topic": topic,
                "interval": interval,
                "producer": producer,
                "next": nxt,
            })

    # ---- DialMQTT-ish public API ----

    def connect(self):
        # For compatibility
        return

    def disconnect(self):
        # For compatibility
        return

    def subscribe(self, topic):
        """
        Record interest in a topic. By default, this mock will emit all topics
        even if you never subscribe. If you'd rather gate emissions by
        subscriptions, set self.emit_only_subscribed = True.
        """
        self._subs.add(topic)

    # Optional knob: if True, only emit topics that were subscribed
    emit_only_subscribed = False

    def poll(self):
        """
        Called frequently by main loop.
        Generates updates for any emission whose timer has elapsed.
        """
        now = time.monotonic()

        for item in self._items:
            if now < item["next"]:
                continue

            # schedule next tick (keeps pace even if we miss cycles)
            # advance in a loop so we don't spam if we're behind
            interval = item["interval"]
            while item["next"] <= now:
                item["next"] += interval

            topic = item["topic"]

            # If gating by subscribe, and nobody subscribed, skip
            if self.emit_only_subscribed and topic not in self._subs:
                continue

            producer = item["producer"]
            try:
                value = producer() if callable(producer) else producer
            except Exception as e:
                print("MockMQTT producer error for", topic, ":", e)
                continue

            self._values[topic] = value
            self._dirty.add(topic)

    def get(self, topic, default=None):
        return self._values.get(topic, default)

    def drain_dirty(self):
        if not self._dirty:
            return None
        topics = set(self._dirty)
        self._dirty.clear()
        return topics