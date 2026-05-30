"""Structured event logging."""

import logging

from world_cup_bot import event_log


def test_log_event_format(caplog):
    caplog.set_level(logging.INFO, logger="world_cup_bot")
    event_log.log_event("plan_abort", abort_reason="cancel_window", dry_run=True)
    assert "event=plan_abort" in caplog.text
    assert "abort_reason=cancel_window" in caplog.text
    assert "dry_run=true" in caplog.text
