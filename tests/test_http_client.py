"""Tests for HTTP client (Cloudflare User-Agent)."""

from world_cup_bot.http_client import USER_AGENT, build_get_request


def test_build_get_request_includes_user_agent():
    req = build_get_request("https://gamma-api.polymarket.com/public-search?q=test")
    assert req.get_header("User-agent") == USER_AGENT
    assert req.get_header("Accept") == "application/json"
