"""Tests for optional webhook alerts."""

import json

from world_cup_bot.alerts import AlertSettings, notify


def test_notify_disabled_when_no_webhook():
    cfg = AlertSettings(webhook_url=None)
    assert not cfg.enabled
    assert notify("test", "hello", settings=cfg) is False


def test_notify_posts_json(monkeypatch):
    cfg = AlertSettings(webhook_url="https://discord.com/api/webhooks/123/abc")
    captured: dict = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=10):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        captured["headers"] = dict(req.header_items())
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert notify("order_cancel", "cancelled 2 orders", extra={"count": 2}, settings=cfg) is True
    assert captured["url"] == "https://discord.com/api/webhooks/123/abc"
    assert captured["body"]["event"] == "order_cancel"
    assert captured["body"]["message"] == "cancelled 2 orders"
    assert captured["body"]["extra"]["count"] == 2


def test_notify_logs_on_failure(monkeypatch):
    cfg = AlertSettings(webhook_url="https://discord.com/api/webhooks/123/abc")

    def boom(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert notify("cross_venue_alert", "gap", settings=cfg) is False


def test_notify_blocks_non_allowlisted_webhook():
    cfg = AlertSettings(webhook_url="https://example.com/hook")
    assert notify("test", "hello", settings=cfg) is False
