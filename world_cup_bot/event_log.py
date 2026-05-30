"""Structured operator logs — stable event= names for grep/Loki-style queries."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("world_cup_bot")


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if " " in text or "=" in text:
        return f'"{text}"'
    return text


def log_event(event: str, **fields: Any) -> None:
    """Emit one INFO line: event=<name> key=value …"""
    parts = [f"event={event}"]
    for key in sorted(fields):
        value = fields[key]
        if value is None:
            continue
        parts.append(f"{key}={_format_value(value)}")
    logger.info(" ".join(parts))
