"""Logging setup: one consistent format for the whole app.

Every record carries the current request ID (the `X-Request-ID` response header), so a
user-reported error can be traced to its log lines. Production logs are one JSON object per
line, which the hosting platform's log viewer can search and filter.
"""

from __future__ import annotations

import json
import logging

from app.core.errors import request_id_var

TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not any(getattr(h, "_mentorx", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler._mentorx = True  # type: ignore[attr-defined]  # idempotent across create_app()
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)
    for h in root.handlers:
        if getattr(h, "_mentorx", False):
            h.setFormatter(JsonFormatter() if json_logs else logging.Formatter(TEXT_FORMAT))
