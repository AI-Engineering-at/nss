"""Lightweight metrics registry for NSS observability.

Provides Counter and Histogram classes with a snapshot export,
avoiding external Prometheus dependencies for the reference implementation.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class Counter:
    """Thread-safe monotonic counter."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._value: float = 0.0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        return self._value


class Histogram:
    """Simple histogram that tracks count, sum, min, max, and recent values."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._count: int = 0
        self._sum: float = 0.0
        self._min: float = float("inf")
        self._max: float = 0.0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._count += 1
            self._sum += value
            self._min = min(self._min, value)
            self._max = max(self._max, value)

    @property
    def count(self) -> int:
        return self._count

    @property
    def avg(self) -> float:
        return self._sum / self._count if self._count else 0.0

    def snapshot(self) -> dict[str, float]:
        return {
            "count": self._count,
            "sum": self._sum,
            "min": self._min if self._count else 0.0,
            "max": self._max,
            "avg": self.avg,
        }


# Pre-defined NSS metrics
nss_requests_total = Counter("nss_requests_total", "Total requests processed")
nss_requests_blocked = Counter("nss_requests_blocked", "Requests blocked by Guardian Shield")
nss_pii_entities_redacted = Counter("nss_pii_entities_redacted", "PII entities redacted")
nss_privacy_budget_consumed = Counter("nss_privacy_budget_consumed", "Total epsilon consumed")
nss_request_latency = Histogram("nss_request_latency_ms", "End-to-end request latency in ms")
nss_guardian_latency = Histogram("nss_guardian_latency_ms", "Guardian Shield processing latency in ms")


def metrics_snapshot() -> dict[str, Any]:
    """Export all metrics as a JSON-serializable dict."""
    return {
        "timestamp": int(time.time()),
        "counters": {
            "nss_requests_total": nss_requests_total.value,
            "nss_requests_blocked": nss_requests_blocked.value,
            "nss_pii_entities_redacted": nss_pii_entities_redacted.value,
            "nss_privacy_budget_consumed": nss_privacy_budget_consumed.value,
        },
        "histograms": {
            "nss_request_latency_ms": nss_request_latency.snapshot(),
            "nss_guardian_latency_ms": nss_guardian_latency.snapshot(),
        },
    }


def prometheus_export() -> str:
    """Export all metrics in Prometheus/OpenMetrics text format."""
    _counters = [
        nss_requests_total,
        nss_requests_blocked,
        nss_pii_entities_redacted,
        nss_privacy_budget_consumed,
    ]
    _histograms = [nss_request_latency, nss_guardian_latency]

    lines: list[str] = []
    for c in _counters:
        lines.append(f"# HELP {c.name} {c.description}")
        lines.append(f"# TYPE {c.name} counter")
        lines.append(f"{c.name} {c.value}")
    for h in _histograms:
        lines.append(f"# HELP {h.name} {h.description}")
        lines.append(f"# TYPE {h.name} histogram")
        lines.append(f"{h.name}_count {h.count}")
        lines.append(f"{h.name}_sum {h._sum}")
    return "\n".join(lines) + "\n"
