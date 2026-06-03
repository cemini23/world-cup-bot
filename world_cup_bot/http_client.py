"""HTTP helpers — Cloudflare rejects bare Python urllib without User-Agent."""

from __future__ import annotations

import ipaddress
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "world-cup-bot/0.1 (+https://github.com/cemini23/world-cup-bot; local-readonly)"

# Outbound GET hosts used by core LP / cross-venue / fixture refresh (WC-SEC-2).
GET_HOST_ALLOWLIST = frozenset(
    {
        "gamma-api.polymarket.com",
        "clob.polymarket.com",
        "data-api.polymarket.com",
        "polymarket.com",
        "api.elections.kalshi.com",
        "raw.githubusercontent.com",
    }
)

WEBHOOK_HOST_ALLOWLIST = frozenset(
    {
        "discord.com",
        "discordapp.com",
        "hooks.slack.com",
        "slack.com",
    }
)

FIXTURE_UPSTREAM_PREFIX = "https://raw.githubusercontent.com/openfootball/"


class HttpUrlNotAllowedError(ValueError):
    """Raised when an operator-controlled or outbound URL fails host policy."""


def _hostname(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise HttpUrlNotAllowedError(f"unsupported URL scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise HttpUrlNotAllowedError(f"invalid URL (no host): {url!r}")
    return host


def _reject_private_host(host: str) -> None:
    """Block literal private/link-local IPs and hostnames that resolve to them."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise HttpUrlNotAllowedError(f"private/reserved IP not allowed: {host}")


def validate_get_url(url: str, *, allowlist: frozenset[str] | None = None) -> None:
    host = _hostname(url)
    _reject_private_host(host)
    allowed = allowlist or GET_HOST_ALLOWLIST
    if host not in allowed:
        raise HttpUrlNotAllowedError(f"GET host not allowlisted: {host}")


def validate_fixture_upstream_url(url: str) -> None:
    if not url.startswith(FIXTURE_UPSTREAM_PREFIX):
        raise HttpUrlNotAllowedError(
            f"fixture upstream must start with {FIXTURE_UPSTREAM_PREFIX!r}"
        )
    validate_get_url(url, allowlist=frozenset({"raw.githubusercontent.com"}))


def validate_webhook_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise HttpUrlNotAllowedError("webhook URL must use HTTPS")
    host = _hostname(url)
    _reject_private_host(host)
    if host not in WEBHOOK_HOST_ALLOWLIST:
        raise HttpUrlNotAllowedError(f"webhook host not allowlisted: {host}")


def build_get_request(url: str) -> urllib.request.Request:
    validate_get_url(url)
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


def urlopen_get_status(url: str, *, timeout: float = 15) -> tuple[int, dict[str, str]]:
    """GET with status + response headers (for rate-limit preflight)."""
    try:
        with urlopen_get(url, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return exc.code, headers
