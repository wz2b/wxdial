# Subscriptions

This document describes the two subscription mechanisms in WxDial: **general pub/sub** and **weather event subscriptions**. These systems allow screens and widgets to receive data updates without tight coupling.

---

## Overview

WxDial has two subscription systems:

1. **General Pub/Sub** (`subscribe.py`) - Topic-based message passing for application events
2. **Weather Events** (`tempest_event.py`) - Specialized system for Tempest WeatherFlow UDP broadcasts

Both use **decorator-based subscriptions** but have different registration and dispatch semantics.

---

## General Pub/Sub

### Basic Usage

```python
from subscribe import subscribe

class MyScreen(Screen):
    @subscribe("temperature")
    def on_temp_update(self, payload):
        self.temp_widget.set(value=payload["temp_f"])
```

### The `@subscribe` Decorator

```python
@subscribe(topic, *, key=None, transform=None)
```

**Parameters:**

* `topic` - String identifier for the message type
* `key` - Optional filter function or key extractor
* `transform` - Optional function to transform payload before delivery

**Subscription registration:**

Subscriptions are stored by function **qualname** (not instance) to work around CircuitPython limitations:

```python
_SUBS = {}  # qualname -> [(topic, key, transform), ...]
```

---

## Weather Event Subscriptions

### The WxEvent System

Weather events come from **Tempest WeatherFlow** devices broadcasting UDP packets on port 50222.

**Key components:**

1. `WxEvent` - Event wrapper
2. `@subscribewx` - Decorator for weather subscriptions
3. `register_wx()` - Binds instance methods
4. `dispatch_wx_event()` - Delivers events to subscribers

---

### WxEvent Structure

```python
class WxEvent:
    __slots__ = ("type", "data", "ts")
```

**Fields:**

* `type` - Event type string (`"obs"`, `"rapid"`, `"device"`, `"hub"`, `"strike"`, `"precip"`)
* `data` - Dictionary payload with decoded fields
* `ts` - Timestamp (monotonic or unix)

**Attribute access:**

`WxEvent` provides dict-like attribute access:

```python
event.temp_f        # -> event.data["temp_f"]
event.wind_speed_mph  # -> event.data["wind_speed_mph"]
```

This makes handler code cleaner:

```python
def on_weather(self, evt):
    # Instead of: temp = evt.data["temp_f"]
    temp = evt.temp_f  # cleaner
```

---

### The `@subscribewx` Decorator

```python
@subscribewx(key=None, transform=None)
```

**Parameters:**

* `key` - Filter: `None` (all), string (exact type match), or predicate function
* `transform` - Optional function to transform event before delivery

**Example - Subscribe to all events:**

```python
@subscribewx()
def on_any_weather(self, event):
    print(f"Got event: {event.type}")
```

**Example - Subscribe to specific type:**

```python
@subscribewx(key="obs")
def on_observation(self, event):
    self.temp_widget.set(value=event.temp_f)
```

**Example - Subscribe with predicate:**

```python
@subscribewx(key=lambda e: e.type == "rapid" and e.wind_speed_mph > 20)
def on_high_wind(self, event):
    self.alert_widget.show_warning()
```

**Example - Subscribe with transform:**

```python
def extract_temp(event):
    return {"temp": event.temp_f, "humidity": event.rh}

@subscribewx(key="obs", transform=extract_temp)
def on_temp_data(self, payload):
    # payload is now the dict from extract_temp(), not WxEvent
    self.update_display(payload["temp"], payload["humidity"])
```

---

### Multiple Subscriptions

A single method can subscribe to multiple event types:

```python
@subscribewx(key="obs")
@subscribewx(key="rapid")
def on_wind_data(self, event):
    if event.type == "obs":
        self.update_avg_wind(event.wind_speed_mph)
    elif event.type == "rapid":
        self.update_gust(event.wind_speed_mph)
```

Internally, this creates a `_WxSubscription` wrapper with multiple `(key, transform)` pairs.

---

### Registration Pattern

Weather subscriptions **must be registered** after instantiation:

```python
from tempest_event import register_wx

class WeatherScreen(Screen):
    def __init__(self):
        super().__init__()
        self.temp_widget = TempWidget()
        
        # Register this instance's subscriptions
        register_wx(self)
    
    @subscribewx(key="obs")
    def on_observation(self, event):
        self.temp_widget.set(value=event.temp_f)
```

**Why registration is needed:**

1. Decorators execute at class definition time
2. CircuitPython doesn't support weak references or method identity
3. We need to bind instance methods to the global listener list

`register_wx()`:

* Inspects the instance's class for `@subscribewx` methods
* Creates bound methods
* Adds them to the global `_WX_LISTENERS` list

---

### Event Dispatch

Events are dispatched by calling:

```python
from tempest_event import dispatch_wx_event

event = WxEvent(type="obs", data=payload, ts=now)
dispatch_wx_event(event)
```

**Dispatch logic:**

1. Iterate all registered listeners
2. Check `key` filter (if any)
3. Apply `transform` (if any)
4. Call handler with payload

**Matching rules:**

* `key=None` → matches all events
* `key="obs"` → matches only `event.type == "obs"`
* `key=lambda e: ...` → matches if predicate returns `True`

**Error handling:**

All exceptions in filters, transforms, and handlers are caught and logged (if `DEBUG=True`). One handler's failure won't prevent others from running.

---

## Tempest Event Types

### obs_st (Observation)

Main weather observation message, sent every minute.

**Key fields:**

```python
{
    "time_epoch": 1234567890,
    "temp_c": 15.2,
    "temp_f": 59.4,
    "rh": 65,                    # relative humidity %
    "pressure_inhg": 29.92,
    "wind_speed_mph": 5.2,
    "wind_dir_deg": 180,
    "rain_prev_min_in": 0.0,
    "uv_index": 3.2,
    "lux": 45000,
    "battery_v": 2.7,
    # ... many more fields
}
```

**Use for:** Primary weather display, trends, logging

---

### rapid_wind (Rapid Wind)

High-frequency wind updates (every 3 seconds).

**Key fields:**

```python
{
    "time_epoch": 1234567890,
    "wind_speed_mph": 12.4,
    "wind_dir_deg": 225,
}
```

**Use for:** Real-time wind gauges, animations

---

### device_status

Device health and diagnostics.

**Key fields:**

```python
{
    "time_epoch": 1234567890,
    "uptime": 3600,
    "voltage": 2.65,
    "rssi": -45,
    "sensor_status": 0,
}
```

**Use for:** Status indicators, battery warnings

---

### evt_strike (Lightning)

Lightning strike detected.

**Key fields:**

```python
{
    "time_epoch": 1234567890,
    "distance_mi": 5.2,
    "energy": 1234,
    "count": 1,  # number of strikes in burst
}
```

**Use for:** Lightning alerts, storm tracking

---

### evt_precip (Rain Start)

Rain detected.

**Key fields:**

```python
{
    "rain_began_epoch": 1234567890,
    "count": 1,
}
```

**Use for:** Rain start notifications

---

### hub_status

Hub device status.

**Key fields:**

```python
{
    "time_epoch": 1234567890,
    "uptime": 86400,
    "rssi": -38,
    "firmware_revision": 171,
}
```

**Use for:** Hub diagnostics

---

## Common Patterns

### Pattern 1: Screen Subscribes, Updates Widgets

Most common pattern - screen receives events and updates child widgets:

```python
class WeatherScreen(Screen):
    def __init__(self):
        super().__init__()
        
        # Create widgets
        self.temp = TempWidget()
        self.wind = WindWidget()
        self.append(self.temp)
        self.append(self.wind)
        
        # Register subscriptions
        register_wx(self)
    
    @subscribewx(key="obs")
    def on_observation(self, event):
        self.temp.set(value=event.temp_f)
        self.wind.set(value=event.wind_speed_mph)
    
    @subscribewx(key="rapid")
    def on_rapid_wind(self, event):
        self.wind.set_gust(event.wind_speed_mph)
```

---

### Pattern 2: Filtered Subscriptions

Only respond to specific conditions:

```python
@subscribewx(key=lambda e: e.type == "obs" and e.temp_f > 90)
def on_high_temp(self, event):
    self.show_heat_warning()

@subscribewx(key=lambda e: e.type == "strike" and e.distance_mi < 5)
def on_nearby_lightning(self, event):
    self.flash_lightning_icon()
```

---

### Pattern 3: Transform for Simplicity

Extract only needed data:

```python
def extract_wind_data(event):
    return {
        "speed": event.wind_speed_mph,
        "direction": event.wind_dir_deg,
        "gust": event.wind_gust_mph,
    }

@subscribewx(key="obs", transform=extract_wind_data)
def on_wind_update(self, data):
    # data is now a simple dict, not WxEvent
    self.wind_widget.set(
        value=data["speed"],
        direction=data["direction"],
        meta=f"Gust: {data['gust']:.1f}"
    )
```

---

### Pattern 4: Multi-Widget Updates

Update multiple widgets from one event:

```python
@subscribewx(key="obs")
def on_full_observation(self, event):
    # Update all dashboard widgets at once
    self.temp.set(value=event.temp_f)
    self.humidity.set(value=event.rh)
    self.pressure.set(value=event.pressure_inhg)
    self.wind_speed.set(value=event.wind_speed_mph)
    self.wind_dir.set(value=event.wind_dir_deg)
    self.rain.set(value=event.rain_prev_min_in)
```

---

### Pattern 5: State Machine Updates

Use events to drive screen state:

```python
class StormScreen(Screen):
    def __init__(self):
        super().__init__()
        self.storm_active = False
        register_wx(self)
    
    @subscribewx(key="strike")
    def on_lightning(self, event):
        if not self.storm_active:
            self.storm_active = True
            self.show_storm_warning()
    
    @subscribewx(key="obs")
    def on_observation(self, event):
        # Clear storm if no lightning for 30 minutes
        if self.storm_active and event.lightning_strike_count == 0:
            self.storm_active = False
            self.hide_storm_warning()
```

---

## UDP Decoder

The `TempestUdpDecoder` converts raw UDP packets to `WxEvent` instances:

```python
from weather.tempest_decode import TempestUdpDecoder

decoder = TempestUdpDecoder(altitude_m=100.0, publish_meta=False)

# In UDP receive loop
data_bytes, addr = sock.recvfrom(4096)
result = decoder.decode(data_bytes, addr)

if result:
    mtype, payload = result
    event = WxEvent(type=mtype, data=payload, ts=time.monotonic())
    dispatch_wx_event(event)
```

**Decoder parameters:**

* `altitude_m` - Station altitude for sea-level pressure correction
* `publish_meta` - Include device serial numbers and metadata in payload

**Output:**

* Returns `(message_type, payload_dict)` or `None` if invalid
* Converts all units to imperial (mph, °F, inHg, inches)
* Calculates sea-level pressure
* Extracts relevant fields from Tempest's array-based format

---

## CircuitPython Constraints

### Why Manual Binding?

CircuitPython limitations that affect the subscription system:

1. **No weak references** - Can't use `weakref.WeakMethod`
2. **Limited introspection** - `__qualname__` may be missing
3. **Method identity** - Same method accessed twice may not be `is` equal
4. **No function attributes** - Can't reliably attach metadata to functions

**Solution:** Store by qualname, manually bind during registration.

---

### The `_BoundWxMethod` Helper

```python
class _BoundWxMethod:
    def __init__(self, fn, instance):
        self.fn = fn
        self.instance = instance
    
    def __call__(self, *args, **kwargs):
        return self.fn(self.instance, *args, **kwargs)
```

This manually creates bound methods because CircuitPython's descriptor protocol isn't fully compatible with our wrapper.

---

### The `_WxSubscription` Wrapper

```python
class _WxSubscription:
    def __init__(self, fn, subscriptions):
        self.fn = fn
        self.subscriptions = subscriptions  # list of (key, transform)
    
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return _BoundWxMethod(self.fn, obj)
```

This wrapper:

* Stores subscription metadata
* Implements the descriptor protocol for method binding
* Allows multiple subscriptions per method

---

## Best Practices

### ✅ Always register weather subscriptions

```python
def __init__(self):
    super().__init__()
    register_wx(self)  # Don't forget this!
```

### ✅ Use transforms to simplify handlers

```python
# Good: handler receives clean data
@subscribewx(key="obs", transform=lambda e: e.temp_f)
def on_temp(self, temp):
    self.widget.set(value=temp)

# Less good: handler does extraction
@subscribewx(key="obs")
def on_temp(self, event):
    self.widget.set(value=event.temp_f)
```

### ✅ Use predicates for complex filtering

```python
# Good: filter at subscription level
@subscribewx(key=lambda e: e.type == "obs" and e.temp_f > 90)
def on_hot(self, event):
    self.show_warning()

# Less good: filter in handler
@subscribewx(key="obs")
def on_obs(self, event):
    if event.temp_f > 90:
        self.show_warning()
```

### ❌ Don't call handlers directly

```python
# Wrong
self.on_observation(event)

# Right - let the dispatch system handle it
dispatch_wx_event(event)
```

### ✅ Handle missing fields gracefully

```python
@subscribewx(key="obs")
def on_obs(self, event):
    # Some fields may be missing or None
    temp = getattr(event, "temp_f", None)
    if temp is not None:
        self.temp.set(value=temp)
```

---

## Debugging

Enable debug output:

```python
# In tempest_event.py
DEBUG = True

# In subscribe.py  
DEBUG = True
```

**Debug output shows:**

* Subscription registration
* Event dispatch
* Handler calls
* Errors in predicates, transforms, and handlers

**Example output:**

```
register_wx: on_observation key= obs
dispatch_wx_event: listeners= 3 event.type= obs
```

---

## Performance Considerations

### Subscription Cost

* Registration: One-time cost during screen initialization
* Dispatch: O(n) where n = number of registered handlers
* Filtering: Cheap predicate evaluation
* Transform: Runs only on matched events

### Optimization Tips

1. **Use specific keys** - `key="obs"` is faster than `key=None`
2. **Simple predicates** - Avoid expensive computations in filter functions
3. **Transform once** - Better to transform at subscription than in every handler
4. **Batch updates** - Update multiple widgets from one handler call

---

## Integration with Main Loop

Typical application structure:

```python
import socket
import time
from weather.tempest_decode import TempestUdpDecoder
from tempest_event import WxEvent, dispatch_wx_event

# Setup
decoder = TempestUdpDecoder(altitude_m=100.0)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", 50222))
sock.setblocking(False)

# Main loop
while True:
    now = time.monotonic()
    
    # Check for UDP packets
    try:
        data, addr = sock.recvfrom(4096)
        result = decoder.decode(data, addr)
        if result:
            mtype, payload = result
            event = WxEvent(type=mtype, data=payload, ts=now)
            dispatch_wx_event(event)
    except OSError:
        pass  # No data available
    
    # Screen lifecycle
    active_screen.tick(now)
    active_screen.refresh()
    
    time.sleep(0.01)
```

**Event flow:**

1. UDP packet arrives → `decoder.decode()`
2. Create `WxEvent` → `dispatch_wx_event()`
3. Screen handlers called → widgets updated
4. `refresh()` renders changes

---

## Summary

| System          | Use Case                | Registration      | Dispatch                 |
| --------------- | ----------------------- | ----------------- | ------------------------ |
| `@subscribe`    | General app events      | Automatic         | Manual `publish()`       |
| `@subscribewx`  | Weather events from UDP | `register_wx()`   | `dispatch_wx_event()`    |

**Key differences:**

* Weather events use instance registration (`register_wx()`)
* Weather events have built-in filtering and transformation
* Weather events are typed (`WxEvent` with `.type` field)

**Design principle:**

Screens orchestrate data flow from subscriptions to widgets. Widgets should not subscribe directly - they receive updates via their parent screen's `set()` method.

This keeps the data flow clear and maintainable:

```
UDP → Event → Screen Handler → Widget.set() → Widget._render()
```
