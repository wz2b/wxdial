# wxdial/router.py
from .subscribe import _SUBS

DEBUG=False

class Router:
    def __init__(self):
        self._handlers = {}  # topic -> [callable(payload)]

    def clear(self):
        self._handlers = {}

    def register(self, obj):
        clsname = obj.__class__.__name__
        if DEBUG:
            print("Router.register:", clsname)

        for name in dir(obj):
            # Skip private-ish names to reduce noise (optional)
            if name.startswith("_"):
                continue

            try:
                bound = getattr(obj, name)
            except Exception:
                continue

            if not callable(bound):
                continue

            # We key subscriptions by "ClassName.method"
            key_qn = clsname + "." + name
            subs = _SUBS.get(key_qn)

            # Fallback: sometimes __qualname__ might be just "method"
            if not subs:
                subs = _SUBS.get(name)

            if not subs:
                continue

            for (topic, k, transform) in subs:
                self._handlers.setdefault(topic, []).append(
                    self._make_handler(bound, k, transform)
                )
                if DEBUG:
                    print("  subscribed:", key_qn, "->", topic)

    def _make_handler(self, bound_method, key, transform):
        def handler(payload):
            # Extract routed value
            if key is None:
                value = payload
            else:
                if payload is None:
                    value = None
                else:
                    try:
                        value = payload.get(key)
                    except AttributeError:
                        value = payload[key]

            # Apply transform
            if transform is not None:
                try:
                    value = transform(value, payload)
                except TypeError:
                    value = transform(payload)

            # Call handler; allow (value) or (value, payload)
            try:
                bound_method(value, payload)
            except TypeError:
                bound_method(value)

        return handler

    def publish(self, topic, payload=None):
        handlers = self._handlers.get(topic)
        if DEBUG:
            print("Router.publish:", topic, "handlers=", 0 if not handlers else len(handlers))

        if not handlers:
            return 0
        for h in handlers:
            h(payload)
        return len(handlers)

    def topics(self):
        """Return an iterable of topic strings currently registered."""
        return self._handlers.keys()    