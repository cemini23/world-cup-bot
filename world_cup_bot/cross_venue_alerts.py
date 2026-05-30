"""Cross-venue scan webhooks — gap alerts, slug changes, verification staleness."""

from __future__ import annotations

from world_cup_bot import alerts
from world_cup_bot.cross_venue_scanner import CrossVenueScanResult


def notify_scan_results(result: CrossVenueScanResult) -> int:
    """Send webhook alerts for actionable scan rows. Returns count sent."""
    sent = 0
    for row in result.alerts:
        line = (
            f"ALERT {row.team} {row.market_type} gap={row.gap_pp:.1f}pp "
            f"PM={row.pm_mid:.3f} KAL={row.kalshi_mid:.3f}"
        )
        if alerts.notify("cross_venue_alert", line, extra=row.to_dict()):
            sent += 1

    for row in result.slug_warnings:
        detail = row.slug_change_detail or "slug changed"
        line = f"SLUG_CHANGE {row.team} {row.market_type}: {detail}"
        if alerts.notify("cross_venue_slug_change", line, extra=row.to_dict()):
            sent += 1

    for row in result.rows:
        if not row.blocked or not row.block_reason:
            continue
        reason = row.block_reason.lower()
        if "stale" not in reason and "last_verified" not in reason:
            continue
        line = f"VERIFY_STALE {row.team} {row.market_type}: {row.block_reason}"
        if alerts.notify("cross_venue_verification_stale", line, extra=row.to_dict()):
            sent += 1

    return sent
