"""Logging with redaction of anything that could describe a person's trip.

Rule: request bodies, query strings, coordinates, bounding boxes, and addresses are never logged
on purpose. This filter is defence in depth for accidental leaks (exceptions, third-party logs).
"""

from __future__ import annotations

import logging
import re
import sys

COORD_PAIR = re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}")
KEYED_VALUE = re.compile(
    r"(?i)(?<![\w-])[\"']?(lat|lon|lng|latitude|longitude|bbox|viewbox|q|query|address|origin|destination|shape|locations?)[\"']?"
    r"\s*[=:]\s*(\[[^\]]*\]|\{[^}]*\}|\"[^\"]*\"|'[^']*'|[^&\s;,}]+)"
)
QUERY_STRING = re.compile(r"\?[A-Za-z0-9_%.+-]+=[^\s\"']*")
DECIMAL_DEGREES = re.compile(r"(?<![\w.])-?(?:1[0-7]\d|\d{1,2})\.\d{4,}(?![\w.])")

REDACTED = "[redacted]"


def redact(text: str) -> str:
    """Mask coordinate-like and address-like content in a log message."""
    out = QUERY_STRING.sub("?" + REDACTED, text)
    out = KEYED_VALUE.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
    out = COORD_PAIR.sub(REDACTED, out)
    out = DECIMAL_DEGREES.sub(REDACTED, out)
    return out


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never let logging crash the app
            record.msg, record.args = "[unformattable log record]", ()
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
    # Uvicorn's access log would contain paths and query strings; it is disabled by the server flag,
    # and its loggers are routed through the redacting handler as well.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("httpcore").setLevel("WARNING")
