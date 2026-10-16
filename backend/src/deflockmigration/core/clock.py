"""Injectable clock so tests can control time."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

Clock = Callable[[], dt.datetime]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
