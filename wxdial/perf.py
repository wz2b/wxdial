import time

class PerfMeter:
    def __init__(self, name, stats):
        self.name = name
        self.stats = stats

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.monotonic() - self.start
        if self.stats is not None:
            self.stats[self.name] = self.stats.get(self.name, 0.0) + dt
