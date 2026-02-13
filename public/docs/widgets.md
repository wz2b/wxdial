# Widgets Lifecycle

This document describes how widgets participate in the WxDial UI lifecycle, including how data flows from the application into display objects.

The design separates **state mutation**, **time-based updates**, and **rendering** into clear phases:

* `set()` → mutate state
* `tick(now)` → time-based logic (optional)
* `refresh()` → push state to display objects

This keeps rendering deterministic and prevents unnecessary display work.

---

## Overview

All widgets inherit from:

```python
class Widget(displayio.Group)
```

A widget is:

* A `displayio.Group`
* A state container (`value`, `meta`, `label`)
* A lifecycle participant (`tick`, `refresh`)
* Responsible for rendering its own children

Widgets are appended to a `Screen`, which is also a `displayio.Group`.

---

## Lifecycle Phases

### 1. set()

Called when new data arrives.

```python
widget.set(value=72)
```

`set()`:

* Updates internal state
* Marks the widget as dirty
* Does NOT immediately redraw

Internally:

```python
self._dirty |= DIRTY_VALUE
```

No display operations happen here.

---

### 2. tick(now)

Called every loop iteration from the active screen.

```python
active.tick(now)
```

Purpose:

* Time-based animation
* State transitions
* Aging / decay logic
* Polling hardware

Default implementation:

```python
def tick(self, now):
    pass
```

Widgets only override this if needed.

**Important:** `tick()` does not render.

---

### 3. refresh()

Called once per main loop after `tick()`.

Main loop pattern:

```python
active.tick(now)
active.refresh()
```

Screen implementation:

```python
def refresh(self):
    for child in self:
        if hasattr(child, "refresh"):
            child.refresh()
```

Widget implementation:

```python
def refresh(self, force=False):
    if force:
        self._dirty = DIRTY_ALL

    if not self._dirty:
        return False

    self._render(self._dirty)
    self._dirty = 0
    return True
```

`refresh()`:

* Checks dirty flags
* Calls `_render()`
* Clears dirty state

Rendering happens **only here**.

---

## Dirty Flags

Widgets use bit flags:

```python
DIRTY_VALUE = 1
DIRTY_LABEL = 2
DIRTY_META  = 4
DIRTY_ALL   = 7
```

`set()` marks specific flags.

`refresh()` passes the flags to `_render()` so subclasses can optimize.

Example:

```python
def _render(self, dirty_flags):
    if dirty_flags & self.DIRTY_VALUE:
        self._label_obj.text = self.format_value()
```

---

## Screen Lifecycle

Screens also inherit from `displayio.Group`.

Order of operations per loop:

1. Input handled
2. `tick(now)` called
3. `refresh()` called
4. Small sleep

Recommended main loop:

```python
while True:
    now = time.monotonic()

    active.tick(now)
    active.refresh()

    time.sleep(0.01)
```

---

## Display Ordering

`displayio.Group` renders in append order:

```python
self.append(background)
self.append(widget)
self.append(overlay)  # topmost
```

Later append = drawn on top.

---

## Nesting Rules

`Screen.refresh()` only calls `refresh()` on **direct children**.

If a widget is nested inside another Group:

```python
group.append(widget)
screen.append(group)
```

Then:

* `screen.refresh()` calls `group.refresh()` (if it exists)
* But will not automatically recurse into children

Therefore:

* Custom widgets should inherit from `Widget`
* And should be appended directly to the Screen unless deliberate nesting is intended

---

## When to Override What

### Override `set()`?

Almost never.

Use base class `set()` unless you need special logic.

---

### Override `tick()`?

Only for:

* Animation
* Time decay
* Blink/spin effects
* Sensor polling

---

### Override `_render()`?

Always.

This is where:

* Text is updated
* Colors change
* Shapes move
* Display objects are mutated

Do not modify display objects outside `_render()` unless absolutely necessary.

---

## Best Practices

### ✅ Use `set()` for data updates

```python
self.temp.set(value=payload.temp_f)
```

### ❌ Do not mutate `.value` directly

```python
self.temp.value = 72   # wrong
```

### ✅ Let refresh handle rendering

Never manually call `_render()`.

### ✅ Keep rendering cheap

Compute geometry in `_render()`, not every loop.

---

## Design Philosophy

This architecture intentionally mirrors game engines and retained-mode UI frameworks:

* State mutation is separate from rendering.
* Rendering only occurs when dirty.
* Tick does logic, refresh does drawing.

This keeps performance predictable and prevents unnecessary display churn on constrained hardware.

---

## Summary

| Phase     | Responsibility   |
| --------- | ---------------- |
| set()     | Update state     |
| tick()    | Time-based logic |
| refresh() | Render if dirty  |

Main loop:

```python
active.tick(now)
active.refresh()
```

Widgets should:

* Never render outside `_render()`
* Never modify display objects inside `set()`
* Use dirty flags correctly