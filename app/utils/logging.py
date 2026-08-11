"""
Structured logging utilities.

Every log call goes through `get_logger()` and events are logged with
`log_event()` so we get consistent, greppable, JSON-friendly structured
logs. API keys / tokens are never logged - `_redact()` scrubs any field
name that looks like a secret as a defense-in-depth measure.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Mapping

_SECRET_KEY_MARKERS = ("token", "key", "secret", "password", "authorization")


def _redact(data: Mapping[str, Any]) -> dict:
    redacted = {}
    for k, v in data.items():
        if any(marker in k.lower() for marker in _SECRET_KEY_MARKERS):
            redacted[k] = "***REDACTED***"
        elif isinstance(v, dict):
            redacted[k] = _redact(v)
        else:
            redacted[k] = v
    return redacted


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": round(time.time(), 3),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "event_data", None)
        if extra:
            payload.update(_redact(extra))
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: str, event: str, **fields: Any) -> None:
    """Log a structured event.

    Example:
        log_event(logger, "info", "project.created", project_id=pid, prompt_len=len(prompt))
    """
    data = {"event": event, **fields}
    getattr(logger, level.lower())(event, extra={"event_data": data})
