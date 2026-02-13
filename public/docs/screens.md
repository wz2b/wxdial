# Screen Lifecycle

This document describes how screens participate in the WxDial UI lifecycle, including navigation, input handling, and the relationship between screens and widgets.

---

## Overview

All screens inherit from:

```python
class Screen(displayio.Group)
```

A screen is:

* A `displayio.Group` container
* A lifecycle participant (`on_show`, `on_hide`, `tick`, `refresh`)
* An input handler (`input()`)
* A widget container (owns child widgets)

Screens are swapped by the application to change what's displayed.

---

## Screen Structure

### Basic Implementation

```python
from screens.screen import Screen

class MyScreen(Screen):
    def __init__(self):
        super().__init__()
        # Add widgets as children
        self.append(my_widget)
```

### Geometry Helpers

Screens provide cached display geometry:

```python
self.width   # Display width
self.height  # Display height
self.cx      # Center X
self.cy      # Center Y
```

These values are:

* Cached at the **class level** (shared by all screens)
* Lazily initialized on first screen instantiation
* Read from `board.DISPLAY` exactly once

This avoids repeated hardware queries and keeps initialization fast.

---

## Lifecycle Methods

### on_show()

Called when this screen becomes the active screen.

```python
def on_show(self):
    """Called when this screen becomes active."""
    pass
```

Use this for:

* Starting animations
* Initializing timers
* Subscribing to data sources
* Resetting state

**Important:** The screen is already in the display tree when `on_show()` is called.

---

### on_hide()

Called when this screen is no longer active.

```python
def on_hide(self):
    """Called when this screen is deactivated."""
    pass
```

Use this for:

* Stopping animations
* Unsubscribing from data sources
* Cleaning up resources
* Pausing background work

**Important:** The screen is still in the display tree when `on_hide()` is called.

---

### tick(now)

Called every main loop iteration while the screen is active.

```python
def tick(self, now):
    """Called periodically for time-based logic."""
    pass
```

**Parameters:**

* `now`: Current time from `time.monotonic()`

**Purpose:**

* Screen-level animations
* Time-based state transitions
* Coordinating widget behavior

**Default behavior:** Does nothing (override only if needed).

**Note:** `tick()` does not render. That happens in `refresh()`.

---

### refresh()

Called once per main loop after `tick()`.

```python
def refresh(self):
    for child in self:
        if hasattr(child, "refresh"):
            child.refresh()
```

**Default behavior:** Calls `refresh()` on all direct children that have the method.

**Important:** This only affects **direct children**. Nested groups must implement their own refresh logic.

**Override:** Rarely needed. The base implementation handles most cases.

---

### input(event_type, event_value=None)

Handles input events sent to the screen.

```python
def input(self, event_type, event_value=None):
    """
    Handle input events.
    
    Return True if handled (consumed), False otherwise.
    """
    return False
```

**Parameters:**

* `event_type`: Type of input (e.g., button press, encoder rotation)
* `event_value`: Optional value (e.g., encoder delta)

**Return value:**

* `True` if the event was handled
* `False` if the event should propagate

**Example:**

```python
def input(self, event_type, event_value=None):
    if event_type == "button_press":
        self.handle_button()
        return True  # consumed
    return False  # not handled
```

---

## Screen Navigation

Screens are activated by the application's screen manager.

**Typical pattern:**

```python
# In main application
current_screen.on_hide()
display.root_group = new_screen
new_screen.on_show()
current_screen = new_screen
```

When switching screens:

1. `on_hide()` called on old screen
2. Display tree updated
3. `on_show()` called on new screen

---

## Main Loop Integration

Recommended main loop structure:

```python
display.root_group = active_screen
active_screen.on_show()

while True:
    now = time.monotonic()
    
    # Handle input
    if event_available():
        active_screen.input(event_type, event_value)
    
    # Update logic
    active_screen.tick(now)
    
    # Render
    active_screen.refresh()
    
    time.sleep(0.01)
```

**Order of operations per frame:**

1. Input handling
2. `tick(now)` for time-based logic
3. `refresh()` for rendering

This keeps input responsive and rendering predictable.

---

## Auto-Rotation

Screens can opt into automatic rotation handling:

```python
def __init__(self):
    super().__init__(wants_auto_rotate=True)
```

**Default:** `wants_auto_rotate=True`

If the application supports rotation, it can check this flag before rotating the screen.

---

## Screen vs Widget Responsibilities

| Responsibility           | Screen | Widget |
| ------------------------ | ------ | ------ |
| Handle input             | ✅      | ❌      |
| Screen navigation        | ✅      | ❌      |
| Coordinate children      | ✅      | ❌      |
| Render specific data     | ❌      | ✅      |
| Own display objects      | ❌      | ✅      |
| Implement dirty tracking | ❌      | ✅      |

**Principle:** Screens orchestrate, widgets render.

---

## Best Practices

### ✅ Initialize widgets in `__init__`

```python
def __init__(self):
    super().__init__()
    self.temp_widget = TempWidget()
    self.append(self.temp_widget)
```

### ✅ Use `on_show()` for activation logic

```python
def on_show(self):
    self.start_animation()
    self.subscribe_to_mqtt()
```

### ✅ Use `on_hide()` for cleanup

```python
def on_hide(self):
    self.stop_animation()
    self.unsubscribe_from_mqtt()
```

### ❌ Don't render in `tick()`

```python
def tick(self, now):
    # Good: update state
    self.elapsed = now - self.start_time
    
    # Bad: render directly
    # self.label.text = str(self.elapsed)  # wrong!
```

Rendering happens in widget `refresh()` methods only.

### ✅ Return input consumption correctly

```python
def input(self, event_type, event_value=None):
    if self.handle_my_input(event_type):
        return True  # consumed
    return False  # let it propagate
```

---

## Display Tree Structure

```
board.DISPLAY
  └─ root_group (Screen instance)
       ├─ widget_1 (Widget instance)
       ├─ widget_2 (Widget instance)
       └─ widget_3 (Widget instance)
```

When a screen is active:

* It is the `root_group` of the display
* All children are in the display tree
* `refresh()` propagates down to widgets

---

## Geometry Caching

The geometry properties are **class-level** and initialized once:

```python
# First screen initialization
screen1 = MyScreen()  # Initializes Screen._width, etc.

# Subsequent screens reuse values
screen2 = OtherScreen()  # No hardware query needed
```

This is safe because:

* Display dimensions don't change at runtime
* All screens share the same display
* Lazy initialization avoids import-time hardware access

---

## Common Patterns

### Simple Static Screen

```python
class WelcomeScreen(Screen):
    def __init__(self):
        super().__init__()
        self.append(WelcomeWidget())
```

No lifecycle overrides needed.

---

### Animated Screen

```python
class LoadingScreen(Screen):
    def __init__(self):
        super().__init__()
        self.spinner = SpinnerWidget()
        self.append(self.spinner)
        
    def on_show(self):
        self.spinner.start()
        
    def on_hide(self):
        self.spinner.stop()
```

Uses `on_show()` and `on_hide()` to control animation.

---

### Interactive Screen

```python
class MenuScreen(Screen):
    def __init__(self):
        super().__init__()
        self.selected_index = 0
        
    def input(self, event_type, event_value=None):
        if event_type == "encoder":
            self.selected_index += event_value
            return True
        return False
```

Handles input and returns consumption status.

---

## Summary

| Method      | Purpose                  | When Called           |
| ----------- | ------------------------ | --------------------- |
| `on_show()` | Activate screen          | Screen becomes active |
| `on_hide()` | Deactivate screen        | Screen becomes hidden |
| `tick()`    | Time-based logic         | Every main loop       |
| `refresh()` | Propagate rendering      | Every main loop       |
| `input()`   | Handle input events      | When input occurs     |

**Screen lifecycle:**

```
Created → on_show() → [tick/refresh loop] → on_hide() → Replaced
```

**Design principle:**

* Screens manage navigation and input
* Widgets manage rendering and state
* Clear separation of concerns keeps code maintainable