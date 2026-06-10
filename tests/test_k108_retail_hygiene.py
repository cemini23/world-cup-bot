"""K108 retail hygiene telemetry."""

from __future__ import annotations

from world_cup_bot.k108_retail_hygiene import (
    load_k108_retail_hygiene,
    negative_filter_telemetry,
    post_fee_mid_edge_pp,
)


def test_load_and_telemetry():
    cfg = load_k108_retail_hygiene()
    telem = negative_filter_telemetry(cfg)
    assert telem["sports_taker_fee_model_pp"] == 0.75
    assert telem["sports_round_trip_fee_pp_high"] == 2.0


def test_post_fee_mid_edge():
    cfg = load_k108_retail_hygiene()
    assert post_fee_mid_edge_pp(5.0, cfg) == 3.0
