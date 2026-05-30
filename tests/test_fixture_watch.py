import json
from pathlib import Path

from world_cup_bot import conviction_patch, fixture_watch


def test_diff_fixtures_rescheduled():
    local = {
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
    upstream = {
        "matches": [
            {
                "date": "2026-06-11",
                "time": "15:00 UTC-6",
                "team1": "Mexico",
                "team2": "South Africa",
                "group": "Group A",
            }
        ]
    }
    changes = fixture_watch.diff_fixtures(local, upstream)
    assert len(changes) == 1
    assert changes[0].change_type == "rescheduled"
    assert "15:00" in changes[0].detail


def test_check_fixtures_in_sync(tmp_path: Path, monkeypatch):
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
    monkeypatch.setattr(
        "world_cup_bot.fixture_watch.fetch_upstream_fixtures",
        lambda _url: json.loads(json.dumps(data, sort_keys=True)),
    )
    result = fixture_watch.check_fixtures(local_path=local)
    assert not result.has_changes


def test_parse_dr_patch_from_fenced_json():
    text = """
Some prose here.

```json
{
  "team": "Morocco",
  "lp_posture": "human_review",
  "review_by": "2026-06-06"
}
```
"""
    patches = conviction_patch.parse_dr_patches(text)
    assert len(patches) == 1
    assert patches[0].team == "Morocco"
    assert patches[0].mode == "human_review"
    assert "per_team:" in conviction_patch.render_staged_yaml(patches)


def test_parse_dr_reduce_with_multiplier():
    obj = {
        "team": "Brazil",
        "lp_posture": "reduce",
        "notional_multiplier": 0.25,
        "max_notional_usd": 500,
    }
    patch = conviction_patch.patch_from_dr_object(obj)
    assert patch is not None
    assert patch.max_notional_usd == 500.0
