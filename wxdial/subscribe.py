# wxdial/subscribe.py

DEBUG = True

_SUBS = {}

def _qualname_of(fn):
    # CircuitPython may not have __qualname__ in all cases
    qn = getattr(fn, "__qualname__", None)
    if qn:
        return qn
    # fallback
    return getattr(fn, "__name__", str(fn))

def subscribe(topic, *, key=None, transform=None):
    """
    Decorator that marks a method as a subscriber for a topic.

    Stored by function qualname because CircuitPython may not allow attaching
    attributes to functions and method identity can be weird.
    """
    def deco(fn):
        qn = _qualname_of(fn)
        lst = _SUBS.get(qn)
        if lst is None:
            lst = []
            _SUBS[qn] = lst
        lst.append((topic, key, transform))
        if DEBUG:
            print("subscribe:", qn, "->", topic)
        return fn
    return deco

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