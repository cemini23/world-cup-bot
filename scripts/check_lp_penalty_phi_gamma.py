#!/usr/bin/env python3
"""K111 P1 — verify gamma ~= 2*phi/sigma^2 (Feys 2606.01477)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from world_cup_bot.inventory_penalty import (  # noqa: E402
    check_phi_gamma_consistency,
    load_inventory_penalty_config,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AS/CJ phi-gamma consistency check")
    p.add_argument("--config", type=Path, default=None)
    args = p.parse_args(argv)
    cfg = load_inventory_penalty_config(args.config)
    ok, msg = check_phi_gamma_consistency(cfg)
    status = "PASS" if ok else "FAIL"
    print(f"inventory_penalty_phi_gamma: {status} — {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
