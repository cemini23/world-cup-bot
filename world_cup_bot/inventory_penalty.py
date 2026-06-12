"""K111 — AS/CJ inventory penalty consistency (Feys 2606.01477)."""

from __future__ import annotations

from pathlib import Path

import yaml

from world_cup_bot.paths import resolve_project_path

_DEFAULT = Path(__file__).resolve().parent.parent / "config" / "inventory_penalty.yaml"


def load_inventory_penalty_config(path: Path | None = None) -> dict:
    p = path or resolve_project_path("config/inventory_penalty.yaml")
    if not p.is_file():
        p = _DEFAULT
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def check_phi_gamma_consistency(cfg: dict) -> tuple[bool, str]:
    phi = float(cfg.get("phi", 0))
    gamma = float(cfg.get("gamma", 0))
    sigma = float(cfg.get("sigma", 0))
    tol = float(cfg.get("max_rel_gamma_error", 0.15))
    if sigma <= 0:
        return False, "sigma must be > 0"
    if gamma <= 0:
        return False, "gamma must be > 0"
    implied = 2.0 * phi / (sigma * sigma)
    rel_err = abs(gamma - implied) / gamma
    msg = (
        f"phi={phi:g} gamma={gamma:g} sigma={sigma:g} "
        f"gamma_implied={implied:g} rel_err={rel_err:.1%} (max {tol:.0%})"
    )
    return rel_err <= tol, msg
