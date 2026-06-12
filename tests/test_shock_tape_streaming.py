import json
from pathlib import Path

from world_cup_bot.shock_tape import load_ticks_for_slugs, parse_tick_line


def test_load_ticks_for_slugs_filters(tmp_path: Path):
    tape = tmp_path / "tape.jsonl"
    rows = [
        {"ts_ms": 1, "price": 0.5, "slug": "fifwc-a-b-mex"},
        {"ts_ms": 2, "price": 0.6, "slug": "other-market"},
        {"ts_ms": 3, "price": 0.55, "slug": "fifwc-a-b-mex"},
    ]
    tape.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    ticks = load_ticks_for_slugs(tape, frozenset({"fifwc-a-b-mex"}))
    assert len(ticks) == 2
    assert all(t.slug == "fifwc-a-b-mex" for t in ticks)


def test_parse_tick_line_basic():
    tick = parse_tick_line({"ts_ms": 100, "price": 0.42, "slug": "x"})
    assert tick is not None
    assert tick.price == 0.42
