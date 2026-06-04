"""Regression: tournament-ops must tolerate omitted fixture upstream URL."""

from __future__ import annotations

import json
from pathlib import Path

from world_cup_bot.fixture_watch import DEFAULT_UPSTREAM_URL, check_fixtures


def test_check_fixtures_none_upstream_uses_default(tmp_path: Path, monkeypatch):
    data = {
        "matches": [
            {
                "date": "2026-06-11",
                "time": "13:00 UTC-6",
                "team1": "Mexico",
                "team2": "South Africa",
                "group": "Group A",
            }
        ]
    }
    local = tmp_path / "fixtures.json"
    local.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")

    def _fetch(url):
        assert url == DEFAULT_UPSTREAM_URL
        return json.loads(json.dumps(data))

    monkeypatch.setattr(
        "world_cup_bot.fixture_watch.fetch_upstream_fixtures",
        _fetch,
    )
    result = check_fixtures(local_path=local, upstream_url=None)
    assert result.upstream_url == DEFAULT_UPSTREAM_URL
    assert not result.has_changes
