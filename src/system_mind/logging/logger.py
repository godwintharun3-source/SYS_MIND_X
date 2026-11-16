"""Contextual logger implementation and logger factory."""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional, TextIO

from system_mind.logging.filter import SensitiveDataRedactingFilter
from system_mind.logging.formatter import StructuredJsonFormatter


class StructuredLogger:
    """Ergonomic structured logger wrapper with immutable context-binding support."""

    def __init__(self, logger: logging.Logger, context: Optional[Dict[str, Any]] = None) -> None:
        self._logger = logger
        self._context: Dict[str, Any] = dict(context or {})

    @property
    def name(self) -> str:
        return self._logger.name

    @property
    def level(self) -> int:
        return self._logger.level

    def bind(self, **kwargs: Any) -> StructuredLogger:
        """Returns a new StructuredLogger instance with additional bound context fields."""
        new_context = dict(self._context)
        new_context.update(kwargs)
        return StructuredLogger(self._logger, new_context)

    def _log(
        self,
        level: int,
        message_or_event: str,
        *args: Any,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        """Dispatches log event with combined bound context and call-site context."""
        if not self._logger.isEnabledFor(level):
            return

        event_name = kwargs.pop("event", message_or_event)
        combined_context = dict(self._context)
        combined_context.update(kwargs)

        extra = {
            "event": event_name,
            "context": combined_context,
            "trace_id": combined_context.get("trace_id"),
            "span_id": combined_context.get("span_id"),
        }

        self._logger.log(
            level,
            message_or_event,
            *args,
            exc_info=exc_info,
            extra=extra,
        )

    def debug(self, message_or_event: str, *args: Any, **kwargs: Any) -> None:
        """Logs a DEBUG level structured event."""
        self._log(logging.DEBUG, message_or_event, *args, **kwargs)

    def info(self, message_or_event: str, *args: Any, **kwargs: Any) -> None:
        """Logs an INFO level structured event."""
        self._log(logging.INFO, message_or_event, *args, **kwargs)

    def warning(self, message_or_event: str, *args: Any, **kwargs: Any) -> None:
        """Logs a WARNING level structured event."""
        self._log(logging.WARNING, message_or_event, *args, **kwargs)

    def error(self, message_or_event: str, *args: Any, exc_info: bool = False, **kwargs: Any) -> None:
        """Logs an ERROR level structured event."""
        self._log(logging.ERROR, message_or_event, *args, exc_info=exc_info, **kwargs)

    def critical(self, message_or_event: str, *args: Any, exc_info: bool = False, **kwargs: Any) -> None:
        """Logs a CRITICAL level structured event."""
        self._log(logging.CRITICAL, message_or_event, *args, exc_info=exc_info, **kwargs)


def configure_logging(
    level: str = "INFO",
    stream: Optional[TextIO] = None,
    logger_name: str = "system_mind",
) -> None:
    """Configures structured logging handler, formatter, and redacting filter."""
    target_logger = logging.getLogger(logger_name)
    num_level = getattr(logging, level.upper(), logging.INFO)
    target_logger.setLevel(num_level)

    # Avoid duplicate handlers if already configured
    target_logger.handlers.clear()

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setLevel(num_level)

    formatter = StructuredJsonFormatter()
    redactor_filter = SensitiveDataRedactingFilter()

    handler.setFormatter(formatter)
    handler.addFilter(redactor_filter)

    target_logger.addHandler(handler)
    target_logger.propagate = False


def get_logger(name: str = "system_mind") -> StructuredLogger:
    """Factory retrieving a configured StructuredLogger."""
    logger = logging.getLogger(name)

    # Ensure at least one handler is present
    if not logger.handlers and not logger.root.handlers:
        configure_logging(logger_name=name)

    return StructuredLogger(logger)
