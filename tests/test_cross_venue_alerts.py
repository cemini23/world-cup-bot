from unittest.mock import patch

from world_cup_bot import cross_venue_alerts
from world_cup_bot.cross_venue_scanner import CrossVenueScanResult, CrossVenueScanRow


def _row(**kwargs) -> CrossVenueScanRow:
    defaults = {
        "team": "USA",
        "market_type": "group_winner",
        "rules_hash": "h1",
        "gap_pp": 6.0,
        "fee_adjusted_gap_pp": 1.1,
        "pm_mid": 0.7,
        "kalshi_mid": 0.64,
        "alert": True,
        "pm_slug": "x",
        "pm_question": "q",
        "kalshi_ticker": "K-USA",
        "kalshi_title": "t",
        "kalshi_volume_24h": 100.0,
        "slug_changed": False,
        "slug_change_detail": None,
        "blocked": False,
        "block_reason": None,
        "notes": None,
        "source": "config",
    }
    defaults.update(kwargs)
    return CrossVenueScanRow(**defaults)


def test_notify_scan_results_sends_alert_and_slug():
    result = CrossVenueScanResult(
        scanned_at="2026-05-30T00:00:00+00:00",
        config_version=1,
        alert_threshold_pp=5.0,
        blockers=(),
        rows=(
            _row(),
            _row(
                team="Switzerland",
                alert=False,
                gap_pp=None,
                slug_changed=True,
                slug_change_detail="slug moved",
            ),
        ),
        discoveries=(),
        pm_market_count=1,
        kalshi_market_count=1,
    )
    with patch("world_cup_bot.cross_venue_alerts.alerts.notify", return_value=True) as notify:
        sent = cross_venue_alerts.notify_scan_results(result)
    assert sent == 2
    events = [call.args[0] for call in notify.call_args_list]
    assert "cross_venue_alert" in events
    assert "cross_venue_slug_change" in events
