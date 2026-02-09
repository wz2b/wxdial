# wxdial/tempest_event.py

DEBUG = False
_WX_LISTENERS = []   # list of tuples: (key, transform, fn)


class WxEvent:
    __slots__ = ("type", "data", "ts")
    def __init__(self, type, data, ts=None):
        self.type = type      # "obs" | "rapid" | "device" | "hub" | ...
        self.data = data      # dict payload
        self.ts = ts          # monotonic() or unix; your call


#############################################################################

def _qualname_of(fn):
    # CircuitPython may not have __qualname__ in all cases
    qn = getattr(fn, "__qualname__", None)
    if qn:
        return qn
    # fallback
    return getattr(fn, "__name__", str(fn))

def subscribewx(key=None, transform=None):
    """
    Decorator for WxEvent listeners.

    key:
      - None: receive all events
      - str: receive only events where event.type == key
      - callable: receive when key(event) is True  (optional but handy)

    transform:
      - None: handler receives WxEvent
      - callable: handler receives transform(event)
    """
    def deco(fn):
        _WX_LISTENERS.append((key, transform, fn))
        if DEBUG:
            print("subscribewx:", _qualname_of(fn), "key=", key, "transform=", transform)
        return fn
    return deco


def dispatch_wx_event(event: WxEvent):
    """
    Call all matching listeners. Returns number of handlers called.
    """
    called = 0
    for key, transform, fn in _WX_LISTENERS:
        # Match
        if key is None:
            ok = True
        elif isinstance(key, str):
            ok = (event.type == key)
        else:
            # treat as predicate
            try:
                ok = bool(key(event))
            except Exception as e:
                if DEBUG:
                    print("subscribewx predicate error:", _qualname_of(fn), e)
                ok = False

        if not ok:
            continue

        # Payload
        payload = event
        if transform is not None:
            try:
                payload = transform(event)
            except Exception as e:
                if DEBUG:
                    print("subscribewx transform error:", _qualname_of(fn), e)
                continue

        # Call
        try:
            fn(payload)
            called += 1
        except Exception as e:
            # Don't let one widget kill the loop
            if DEBUG:
                print("subscribewx handler error:", _qualname_of(fn), e)

    return called
