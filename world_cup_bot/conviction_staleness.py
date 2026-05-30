"""Mid staleness alerts — ledger mid_at_place vs live Gamma (conviction DR trigger)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from world_cup_bot.ledger import load_rows
from world_cup_bot.scanner import AdvanceMarket


@dataclass(frozen=True)
class MidStalenessAlert:
    team: str
    mid_at_place: float
    live_mid: float
    delta_pp: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "mid_at_place": self.mid_at_place,
            "live_mid": self.live_mid,
            "delta_pp": round(self.delta_pp, 2),
            "reason": self.reason,
        }


def last_quote_mid_by_team(ledger_path: Path) -> dict[str, float]:
    """Most recent quote_intent mid_at_place per team from ledger."""
    rows = load_rows(ledger_path)
    out: dict[str, float] = {}
    for row in reversed(rows):
        if row.get("event") not in ("quote_intent", "quote_intent_dry_run"):
            continue
        team = row.get("team")
        mid = row.get("mid_at_place")
        if not team or mid is None:
            continue
        if team not in out:
            out[str(team)] = float(mid)
    return out


def scan_mid_staleness(
    markets: list[AdvanceMarket],
    *,
    ledger_path: Path,
    threshold_pp: float = 15.0,
) -> list[MidStalenessAlert]:
    """Flag teams whose live mid moved ≥ threshold_pp since last recorded quote."""
    baseline = last_quote_mid_by_team(ledger_path)
    if not baseline:
        return []

    live_by_team = {m.team: m for m in markets if m.mid is not None}
    alerts: list[MidStalenessAlert] = []

    for team, placed_mid in baseline.items():
        market = live_by_team.get(team)
        if market is None or market.mid is None:
            continue
        delta_pp = abs(market.mid - placed_mid) * 100.0
        if delta_pp < threshold_pp:
            continue
        alerts.append(
            MidStalenessAlert(
                team=team,
                mid_at_place=placed_mid,
                live_mid=market.mid,
                delta_pp=delta_pp,
                reason=(
                    f"mid moved {delta_pp:.1f}pp since last quote "
                    f"({placed_mid:.3f} → {market.mid:.3f}) — re-run conviction DR"
                ),
            )
        )

    alerts.sort(key=lambda a: -a.delta_pp)
    return alerts
