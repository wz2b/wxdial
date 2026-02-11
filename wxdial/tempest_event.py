# wxdial/tempest_event.py

DEBUG = True
_WX_LISTENERS = []  # list of (key, transform, bound_fn)


class WxEvent:
    __slots__ = ("type", "data", "ts")
    def __init__(self, type, data, ts=None):
        self.type = type      # "obs" | "rapid" | "device" | "hub" | ...
        self.data = data      # dict payload
        self.ts = ts          # monotonic() or unix; your call

    def __getattr__(self, name):
        # Only called if normal attribute lookup fails
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(
                "WxEvent has no attribute {!r}".format(name)

    def __repr__(self):
        return f"<WxEvent type={self.type!r} data_keys={list(self.data.keys()) if isinstance(self.data, dict) else type(self.data)}>"


#############################################################################

def _qualname_of(fn):
    qn = getattr(fn, "__qualname__", None)
    if qn:
        return qn
    return getattr(fn, "__name__", str(fn))


class _BoundWxMethod:
    """Manually bound method for CircuitPython"""
    def __init__(self, fn, instance):
        self.fn = fn
        self.instance = instance
    
    def __call__(self, *args, **kwargs):
        return self.fn(self.instance, *args, **kwargs)


class _WxSubscription:
    """Wrapper that holds subscription metadata"""
    def __init__(self, fn, subscriptions):
        self.fn = fn
        self.subscriptions = subscriptions  # list of (key, transform)
        self.__name__ = fn.__name__
        self.__qualname__ = getattr(fn, "__qualname__", fn.__name__)
    
    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)
    
    def __get__(self, obj, objtype=None):
        """Support binding as a method"""
        if obj is None:
            return self
        # Manually create a bound method
        return _BoundWxMethod(self.fn, obj)


def subscribewx(key=None, transform=None):
    def deco(fn):
        # If already wrapped, add to existing subscriptions
        if isinstance(fn, _WxSubscription):
            fn.subscriptions.append((key, transform))
            return fn
        
        # Otherwise, wrap it
        wrapper = _WxSubscription(fn, [(key, transform)])
        return wrapper
    return deco


def register_wx(obj):
    """Bind and register any @subscribewx methods on obj."""
    n = 0
    
    # We need to look at the CLASS, not the instance
    for name in dir(obj):
        try:
            # Get from the CLASS to access the descriptor itself
            class_attr = getattr(type(obj), name, None)
            if class_attr is None:
                continue
            
            # Check if it's our wrapper
            if isinstance(class_attr, _WxSubscription):
                # Now get the BOUND method from the instance
                bound_method = getattr(obj, name)
                for (key, transform) in class_attr.subscriptions:
                    _WX_LISTENERS.append((key, transform, bound_method))
                    n += 1
                    if DEBUG:
                        print("register_wx:", name, "key=", key)
        except Exception as e:
            if DEBUG:
                print(f"Error processing {name}: {e}")
            continue
    
    return n


def dispatch_wx_event(event: WxEvent):
    if DEBUG:
        print("dispatch_wx_event: listeners=", len(_WX_LISTENERS), "event.type=", getattr(event, "type", None))

    called = 0
    for key, transform, fn in _WX_LISTENERS:
        # Match
        if key is None:
            ok = True
        elif isinstance(key, str):
            ok = (event.type == key)
        else:
            try:
                ok = bool(key(event))
            except Exception as e:
                if DEBUG:
                    print("subscribewx predicate error:", e)
                ok = False

        if not ok:
            continue

        payload = event
        if transform is not None:
            try:
                payload = transform(event)
            except Exception as e:
                if DEBUG:
                    print("subscribewx transform error:", e)
                continue

        try:
            fn(payload)   # fn is BOUND, so self is already included
            called += 1
        except Exception as e:
            if DEBUG:
                print("subscribewx handler error:", e)

    return called