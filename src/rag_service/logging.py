"""Structured logging and request-scoped correlation IDs."""

from __future__ import annotations

import contextvars
import logging
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get() or "-"
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s"))
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_extra(**fields: Any) -> dict[str, Any]:
    """Construct structured log extras without exposing secret/raw document content."""

    return {key: value for key, value in fields.items() if value is not None}
