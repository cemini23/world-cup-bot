"""Tests for HTTP client (Cloudflare User-Agent + outbound allowlist)."""

import pytest

from world_cup_bot.http_client import (
    USER_AGENT,
    HttpUrlNotAllowedError,
    build_get_request,
    validate_fixture_upstream_url,
    validate_get_url,
    validate_webhook_url,
)


def test_build_get_request_includes_user_agent():
    req = build_get_request("https://gamma-api.polymarket.com/public-search?q=test")
    assert req.get_header("User-agent") == USER_AGENT
    assert req.get_header("Accept") == "application/json"


def test_validate_get_rejects_unknown_host():
    with pytest.raises(HttpUrlNotAllowedError, match="not allowlisted"):
        validate_get_url("https://evil.example.com/path")


def test_validate_get_rejects_private_ip():
    with pytest.raises(HttpUrlNotAllowedError, match="private"):
        validate_get_url("http://127.0.0.1/time")


def test_validate_webhook_requires_https():
    with pytest.raises(HttpUrlNotAllowedError, match="HTTPS"):
        validate_webhook_url("http://discord.com/api/webhooks/x")


def test_validate_webhook_allows_discord():
    validate_webhook_url("https://discord.com/api/webhooks/123/abc")


def test_validate_fixture_upstream_prefix():
    validate_fixture_upstream_url(
        "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
    )
    with pytest.raises(HttpUrlNotAllowedError):
        validate_fixture_upstream_url("https://raw.githubusercontent.com/other/repo/file.json")
