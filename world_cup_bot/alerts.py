"""Optional operator alerts — webhook POST (stdlib, no extra deps)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertSettings:
    webhook_url: str | None

    @classmethod
    def from_env(cls) -> AlertSettings:
        url = os.environ.get("WC_ALERT_WEBHOOK_URL", "").strip()
        return cls(webhook_url=url or None)

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)


def notify(
    event: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
    settings: AlertSettings | None = None,
) -> bool:
    """POST alert to WC_ALERT_WEBHOOK_URL if configured. Returns True when sent."""
    cfg = settings or AlertSettings.from_env()
    if not cfg.enabled:
        return False

    payload: dict[str, Any] = {
        "event": event,
        "message": message,
        "source": "world-cup-bot",
    }
    if extra:
        payload["extra"] = extra

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        cfg.webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "world-cup-bot/alerts"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                logger.warning("webhook HTTP %s for event=%s", resp.status, event)
                return False
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("webhook failed event=%s: %s", event, exc)
        return False

    logger.info("webhook sent event=%s", event)
    return True
