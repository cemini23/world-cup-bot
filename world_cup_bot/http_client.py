"""HTTP helpers — Cloudflare rejects bare Python urllib without User-Agent."""

from __future__ import annotations

import urllib.request
from typing import Any

USER_AGENT = "world-cup-bot/0.1 (+https://github.com/cemini23/world-cup-bot; local-readonly)"


def build_get_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )


def urlopen_get(url: str, *, timeout: float = 30) -> Any:
    return urllib.request.urlopen(build_get_request(url), timeout=timeout)
