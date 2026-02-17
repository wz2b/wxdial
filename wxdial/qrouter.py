# wxdial/subscribe.py
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

class QueuedRouter(Router):
    def __init__(self, max_queue=32):
        super().__init__()
        self._q = []
        self._max = max_queue

    def publish(self, topic, payload=None):
        # queue; drop oldest if full (or drop newest, your choice)
        if len(self._q) >= self._max:
            self._q.pop(0)
        self._q.append((topic, payload))
        return 1

    def dispatch_all(self):
        n = 0
        while self._q:
            topic, payload = self._q.pop(0)
            n += super().publish(topic, payload)
        return n

