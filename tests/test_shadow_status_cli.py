"""shadow-status CLI gate."""

import json
from argparse import Namespace

from world_cup_bot import __main__


def test_shadow_status_passes_when_steps_done(monkeypatch):
    payload = {
        "dry_run": True,
        "shadow_progress": "2/5",
        "shadow_steps": [
            {"id": "a", "phase": 0, "title": "t", "detail": "d", "status": "done"},
            {"id": "b", "phase": 1, "title": "t2", "detail": "d2", "status": "done"},
        ],
        "ledger": {"quote_intents": 1, "fills": 0, "distinct_days": 1},
    }
    monkeypatch.setattr(__main__.shadow_checklist, "ready_payload", lambda *a, **k: payload)
    rc = __main__._cmd_shadow_status(Namespace(min_phase=1, json=False, skip_auth=True))
    assert rc == 0


def test_shadow_status_fails_on_pending(monkeypatch, capsys):
    payload = {
        "dry_run": True,
        "shadow_progress": "1/5",
        "shadow_steps": [
            {"id": "a", "phase": 1, "title": "t", "detail": "d", "status": "pending"},
        ],
        "ledger": {"quote_intents": 0, "fills": 0, "distinct_days": 0},
    }
    monkeypatch.setattr(__main__.shadow_checklist, "ready_payload", lambda *a, **k: payload)
    rc = __main__._cmd_shadow_status(Namespace(min_phase=1, json=False, skip_auth=True))
    assert rc == 1


def test_shadow_status_json_output(monkeypatch, capsys):
    payload = {"dry_run": True, "shadow_progress": "0/0", "shadow_steps": [], "ledger": {}}
    monkeypatch.setattr(__main__.shadow_checklist, "ready_payload", lambda *a, **k: payload)
    rc = __main__._cmd_shadow_status(Namespace(min_phase=0, json=True, skip_auth=True))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
