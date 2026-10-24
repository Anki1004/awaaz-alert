"""Minimal Prometheus text-format metrics (no dependency). Counters and one latency histogram; no labels that could
carry call content."""
from __future__ import annotations

import threading

_BUCKETS = (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)


class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.counters: dict[str, float] = {}
        self.gauges: dict[str, float] = {}
        self.lat_counts = [0] * len(_BUCKETS)
        self.lat_sum, self.lat_n = 0.0, 0

    def inc(self, name: str, v: float = 1.0):
        with self.lock:
            self.counters[name] = self.counters.get(name, 0.0) + v

    def gauge(self, name: str, v: float):
        with self.lock:
            self.gauges[name] = v

    def observe_latency(self, seconds: float):
        with self.lock:
            self.lat_sum += seconds
            self.lat_n += 1
            for i, b in enumerate(_BUCKETS):
                if seconds <= b:
                    self.lat_counts[i] += 1

    def render(self) -> str:
        with self.lock:
            out = []
            for k, v in sorted(self.counters.items()):
                out += [f"# TYPE awaaz_{k} counter", f"awaaz_{k} {v:g}"]
            for k, v in sorted(self.gauges.items()):
                out += [f"# TYPE awaaz_{k} gauge", f"awaaz_{k} {v:g}"]
            out.append("# TYPE awaaz_window_latency_seconds histogram")
            for b, c in zip(_BUCKETS, self.lat_counts):
                out.append(f'awaaz_window_latency_seconds_bucket{{le="{b}"}} {c}')
            out += [f'awaaz_window_latency_seconds_bucket{{le="+Inf"}} {self.lat_n}',
                    f"awaaz_window_latency_seconds_sum {self.lat_sum:.4f}", f"awaaz_window_latency_seconds_count {self.lat_n}"]
            return "\n".join(out) + "\n"


METRICS = Metrics()
