"""Tests for pmxt parquet → JSONL converter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("pyarrow")
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "shock_backtest"))
import pmxt_parquet_to_jsonl as conv  # noqa: E402


def test_parquet_convert_football_filter(tmp_path: Path):
    table = pa.table(
        {
            "slug": ["epl-man-united-win", "will-trump-win-2028"],
            "timestamp": [1_000_000_000_000, 1_000_000_001_000],
            "price": [0.30, 0.55],
            "bids": [
                [{"price": 0.29, "size": 100.0}],
                [{"price": 0.54, "size": 50.0}],
            ],
        }
    )
    pq_path = tmp_path / "sample.parquet"
    pq.write_table(table, pq_path)
    out = tmp_path / "out.jsonl"
    stats = conv.convert_files(
        [pq_path],
        out,
        include=("epl", "world-cup", "fifa"),
        exclude=("advance",),
        append=False,
    )
    assert stats["events_out"] >= 1
    lines = out.read_text().strip().splitlines()
    assert all("epl-man-united" in ln for ln in lines)
    first = json.loads(lines[0])
    assert first["slug"] == "epl-man-united-win"


def test_parquet_convert_condition_id_with_resolver(tmp_path: Path):
    table = pa.table(
        {
            "market": [b"0x00000977017fa72fb6b1908ae694000d3b51f442c2552656b10bdbbfd16ff707"],
            "timestamp_received": [1_000_000_000_000],
            "price": [0.30],
            "best_bid": [0.29],
            "best_ask": [0.31],
        }
    )
    pq_path = tmp_path / "v2.parquet"
    pq.write_table(table, pq_path)
    out = tmp_path / "out.jsonl"

    class FakeResolver:
        def resolve(self, condition_id: str) -> str | None:
            return "epl-test-fc-vs-other-fc"

    stats = conv.convert_files(
        [pq_path],
        out,
        include=("epl",),
        exclude=(),
        append=False,
        resolver=FakeResolver(),
        prefetch=False,
    )
    assert stats["events_out"] >= 1
    first = json.loads(out.read_text().strip().splitlines()[0])
    assert first["slug"] == "epl-test-fc-vs-other-fc"


def test_prefetch_football_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cid = "0x00000977017fa72fb6b1908ae694000d3b51f442c2552656b10bdbbfd16ff707"
    table = pa.table(
        {
            "market": [cid.encode(), cid.encode()],
            "timestamp_received": [1_000_000_000_000, 1_000_000_001_000],
            "price": [0.30, 0.31],
            "best_bid": [0.29, 0.30],
            "best_ask": [0.31, 0.32],
        }
    )
    pq_path = tmp_path / "v2.parquet"
    pq.write_table(table, pq_path)
    out = tmp_path / "out.jsonl"

    def fake_prefetch(ids, *, include, exclude, batch_size=40, sleep_s=0.02):
        assert len(ids) == 1
        return {cid.lower(): "epl-test-fc-vs-other-fc"}

    monkeypatch.setattr(conv, "prefetch_football_slugs", fake_prefetch)
    stats = conv.convert_files(
        [pq_path],
        out,
        include=("epl",),
        exclude=(),
        append=False,
    )
    assert stats["football_markets"] == 1
    assert stats["events_out"] >= 2
