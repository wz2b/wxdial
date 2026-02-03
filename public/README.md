# WXS Sprite Format – Design Rationale and Evolution

## Background

The original animation pipeline used sprite sheets stored as BMP files:

- Each animation was a single wide bitmap
- Height = tile height (usually 64 px)
- Width = tile width × number of frames
- Frames selected via `displayio.TileGrid`

This works well on disk, but causes problems on constrained devices when attempting
to optimize storage or memory usage.

---

## Problem: RAM Constraints on Embedded Devices

On the target device (ESP32-S3 / M5Dial running CircuitPython):

- `displayio.Bitmap` allocations require **contiguous RAM**
- `zlib.decompress()` produces a full uncompressed buffer in memory
- Garbage collection does **not defragment** memory

Attempting to load a compressed sprite sheet into RAM caused:

- Multiple large temporary allocations
- Heap fragmentation
- Frequent `MemoryError` failures when allocating ~50–70 KB blocks

Even aggressive cleanup (`gc.collect()`, dropping references) proved unreliable.

---

## WXS1 (Abandoned)

### Format
- One zlib-compressed blob containing **all frames**
- At load time:
  - Entire blob decompressed
  - Full sprite sheet bitmap created in RAM

### Why it failed
- Peak RAM usage included:
  - Compressed blob
  - Full decompressed pixel buffer
  - Full sprite sheet bitmap
- Required large contiguous allocations
- Fragile and unreliable on-device

---

## WXS2 (Current Design)

### Core Insight
**The device never needs all frames in RAM at once.**

Animations are temporal, not spatial.

---

### WXS2 File Format

A WXS2 file contains:

1. **Header**
   - Magic: `"WXS2"`
   - Tile width / height
   - Frame count
   - Palette size
   - Alpha threshold

2. **Palette**
   - Shared palette for all frames
   - Index 0 reserved for transparency

3. **Frame Table**
   - For each frame:
     - Offset (uint32)
     - Length (uint32)
   - Allows random access to frames on disk

4. **Frame Data**
   - Each frame stored as its own zlib-compressed blob
   - One frame = `tile_w × tile_h` bytes uncompressed

---

### Runtime Behavior (Critical Difference)

Instead of loading everything:

- Allocate **one bitmap** of size `tile_w × tile_h`
- On each animation step:
  1. Seek to the frame’s compressed blob
  2. Read it
  3. `zlib.decompress()` (≈4 KB)
  4. Copy pixels into the bitmap
  5. Discard decompressed buffer

Peak RAM usage stays small and constant.

---

### Advantages

- ✔ Full animation fidelity preserved
- ✔ Constant, low RAM usage
- ✔ No large contiguous allocations
- ✔ Resistant to heap fragmentation
- ✔ Storage-efficient via zlib compression
- ✔ Compatible with palette transparency

---

## Why Not TileGrid Frames?

`TileGrid` frame indexing requires all frames to exist in a single bitmap.

WXS2 trades TileGrid frame indexing for:
- Single-frame bitmap updates
- Explicit frame loading

This is an intentional tradeoff to meet memory constraints.

---

## Summary

WXS2 is not a compression trick — it is a **memory architecture change**.

By shifting frames from RAM to disk and loading them on demand, we preserve
animation quality while making the system reliable on constrained hardware.

This fork was necessary to align the animation model with embedded reality.
