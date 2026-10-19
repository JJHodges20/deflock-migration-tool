"""Process-local service metrics without trip data (roadmap sections 13 and 16).

Counts and latency summaries only: route templates, status codes, durations, plan outcomes, and search
sizes. No coordinates, addresses, shapes, request bodies, or query strings are ever recorded. Samples live
in bounded in-memory reservoirs and vanish with the process; nothing is written to disk or a database.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field

MAX_SAMPLES = 512


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _summary(samples: deque[float]) -> dict:
    values = list(samples)
    return {
        "samples": len(values),
        "p50_ms": round(_percentile(values, 0.5), 1) if values else None,
        "p95_ms": round(_percentile(values, 0.95), 1) if values else None,
        "max_ms": round(max(values), 1) if values else None,
    }


@dataclass
class _RouteStats:
    count: int = 0
    errors: int = 0  # status >= 500
    rejected: int = 0  # status 400-499
    durations_ms: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))


class Metrics:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic, max_samples: int = MAX_SAMPLES):
        self._clock = clock
        self._started = clock()
        self._lock = threading.Lock()
        self._max = max_samples
        self._routes: dict[str, _RouteStats] = {}
        self._plans = 0
        self._plan_status: Counter[str] = Counter()
        self._plan_options: Counter[int] = Counter()
        self._plan_calls = 0
        self._plan_elapsed_ms: deque[float] = deque(maxlen=max_samples)
        self._plan_errors: Counter[str] = Counter()

    def observe_request(self, route_template: str, status: int, duration_ms: float) -> None:
        """`route_template` is the declared path pattern (for example `/api/v1/routes/plan`), never the raw URL."""
        with self._lock:
            stats = self._routes.setdefault(route_template, _RouteStats(durations_ms=deque(maxlen=self._max)))
            stats.count += 1
            if status >= 500:
                stats.errors += 1
            elif status >= 400:
                stats.rejected += 1
            stats.durations_ms.append(float(duration_ms))

    def observe_plan(self, *, search_status: str, option_count: int, routing_calls: int, elapsed_s: float) -> None:
        with self._lock:
            self._plans += 1
            self._plan_status[search_status] += 1
            self._plan_options[int(option_count)] += 1
            self._plan_calls += int(routing_calls)
            self._plan_elapsed_ms.append(float(elapsed_s) * 1000.0)

    def observe_plan_error(self, code: str) -> None:
        with self._lock:
            self._plan_errors[code] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "uptime_seconds": round(self._clock() - self._started, 1),
                "requests": {template: {"count": s.count, "rejected_4xx": s.rejected, "errors_5xx": s.errors, **_summary(s.durations_ms)} for template, s in sorted(self._routes.items())},
                "plans": {
                    "count": self._plans,
                    "by_search_status": dict(self._plan_status),
                    "options_returned": {str(k): v for k, v in sorted(self._plan_options.items())},
                    "routing_calls_total": self._plan_calls,
                    "errors_by_code": dict(self._plan_errors),
                    **{f"elapsed_{k}": v for k, v in _summary(self._plan_elapsed_ms).items() if k != "samples"},
                },
                "meaning": "Counts and latency summaries kept in memory since the process started; no trip, address, coordinate, or geometry is recorded.",
            }


def process_memory_mb() -> float | None:
    """Resident set size from the kernel on Linux; None elsewhere. Never raises."""
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except OSError:
        return None
    return None
