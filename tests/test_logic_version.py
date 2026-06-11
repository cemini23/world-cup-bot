from world_cup_bot.logic_version import (
    LEGACY_UNVERSIONED,
    PnlScope,
    filter_rows_by_scope,
    load_strategy_version,
)


def test_load_registry():
    spec = load_strategy_version()
    assert spec.strategy_key == "pm_wc_advance_lp"
    assert spec.version_id == "wc_advance_lp_v8"
    assert LEGACY_UNVERSIONED in spec.legacy_version_ids


def test_version_banner():
    spec = load_strategy_version()
    banner = spec.version_banner()
    assert "pm_wc_advance_lp" in banner
    assert "wc_advance_lp_v8" in banner


def test_scope_legacy():
    spec = load_strategy_version()
    rows = [
        {"logic_version": spec.version_id},
        {"logic_version": "wc_advance_lp_v0"},
        {"logic_version": LEGACY_UNVERSIONED},
    ]
    legacy = filter_rows_by_scope(rows, spec, PnlScope.LEGACY)
    versions = {r["logic_version"] for r in legacy}
    assert spec.version_id not in versions
    assert LEGACY_UNVERSIONED in versions
