from world_cup_bot.inventory_penalty import (
    check_phi_gamma_consistency,
    load_inventory_penalty_config,
)


def test_phi_gamma_consistent_k111_defaults():
    cfg = load_inventory_penalty_config()
    ok, _ = check_phi_gamma_consistency(cfg)
    assert ok


def test_phi_gamma_detects_drift():
    ok, msg = check_phi_gamma_consistency(
        {"phi": 0.01, "gamma": 0.8, "sigma": 0.05, "max_rel_gamma_error": 0.15}
    )
    assert not ok
    assert "rel_err" in msg
