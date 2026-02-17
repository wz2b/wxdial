# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

import gc
import time

class PerfMeter:
    __slots__ = ("name", "stats", "start")

    def __init__(self, name, stats):
        self.name = name
        self.stats = stats
        self.start = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.monotonic() - self.start
        s = self.stats
        if s is None:
            return False  # don't suppress exceptions

        row = s.get(self.name)
        if row is None:
            # [total_seconds, count, max_seconds]
            s[self.name] = [dt, 1, dt]
        else:
            row[0] += dt
            row[1] += 1
            if dt > row[2]:
                row[2] = dt

        return False  # don't suppress exceptions



def print_perf(stats):
    print("\n--- Performance Stats ---")
    for name, row in stats.items():
        if isinstance(row, list) and len(row) == 3:
            total, count, mx = row
            avg = total / count if count else 0.0
            print(f"{name}: total={total:.3f}s avg={avg:.3f}s max={mx:.3f}s n={count}")
        else:
            # fallback if you still have old float entries
            print(f"{name}: {row}")
    print("mem_free:", gc.mem_free())
    print("-------------------------")

