"""Strategy logic version registry — mirrors Cemini prod pnl-attribution-versioning pattern."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import yaml

DEFAULT_REGISTRY = (
    Path(__file__).resolve().parent.parent / "config" / "strategy_logic_versions.yaml"
)
LEGACY_UNVERSIONED = "legacy_unversioned"


class PnlScope(StrEnum):
    CURRENT = "current"
    LEGACY = "legacy"
    ALL = "all"


@dataclass(frozen=True)
class StrategyVersionSpec:
    strategy_key: str
    version_id: str
    deployed_at: datetime
    note: str
    legacy_version_ids: frozenset[str]

    def version_banner(self) -> str:
        return (
            f"strategy={self.strategy_key} logic_version={self.version_id} "
            f"deployed={self.deployed_at.isoformat()}"
        )


def load_strategy_version(path: Path | None = None) -> StrategyVersionSpec:
    p = path or DEFAULT_REGISTRY
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    current = raw.get("current") or {}
    legacy = raw.get("legacy_version_ids") or [LEGACY_UNVERSIONED]
    deployed_raw = current.get("deployed_at", "1970-01-01T00:00:00Z")
    if isinstance(deployed_raw, str) and deployed_raw.endswith("Z"):
        deployed = datetime.fromisoformat(deployed_raw.replace("Z", "+00:00"))
    else:
        deployed = datetime.fromisoformat(str(deployed_raw))

    return StrategyVersionSpec(
        strategy_key=str(raw.get("strategy_key", "pm_wc_advance_lp")),
        version_id=str(current.get("version_id", LEGACY_UNVERSIONED)),
        deployed_at=deployed,
        note=str(current.get("note", "")),
        legacy_version_ids=frozenset(str(x) for x in legacy),
    )


def filter_rows_by_scope(
    rows: list[dict],
    spec: StrategyVersionSpec,
    scope: PnlScope,
) -> list[dict]:
    """Drop legacy rows from headline PnL when scope=current (K75 default)."""
    if scope == PnlScope.ALL:
        return rows

    current_id = spec.version_id
    legacy_ids = set(spec.legacy_version_ids) | {LEGACY_UNVERSIONED}

    def row_version(row: dict) -> str:
        v = row.get("logic_version")
        if v is None or str(v).strip() == "":
            return LEGACY_UNVERSIONED
        return str(v)

    if scope == PnlScope.CURRENT:
        return [r for r in rows if row_version(r) == current_id]
    # legacy
    return [r for r in rows if row_version(r) in legacy_ids and row_version(r) != current_id]
