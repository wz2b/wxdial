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

