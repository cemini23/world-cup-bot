"""Runtime configuration from environment (no secrets in repo)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from world_cup_bot.paths import resolve_project_path


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    gamma_url: str
    clob_url: str
    ws_user_url: str
    dry_run: bool
    min_hours_before_kickoff: float
    max_notional_per_market_usd: float
    conviction_config: str
    logic_version_config: str
    ledger_path: str
    operating_config: str
    cross_venue_config: str
    kalshi_base_url: str
    market_phases_config: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            gamma_url=os.environ.get(
                "POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com"
            ).rstrip("/"),
            clob_url=os.environ.get("POLYMARKET_CLOB_URL", "https://clob.polymarket.com").rstrip(
                "/"
            ),
            ws_user_url=os.environ.get(
                "POLYMARKET_WS_USER_URL",
                "wss://ws-subscriptions-clob.polymarket.com/ws/user",
            ),
            dry_run=_bool("DRY_RUN", True),
            min_hours_before_kickoff=_float("MIN_HOURS_BEFORE_KICKOFF", 10.0),
            max_notional_per_market_usd=_float("MAX_NOTIONAL_PER_MARKET_USD", 2000.0),
            conviction_config=str(
                resolve_project_path(os.environ.get("CONVICTION_CONFIG", "config/conviction.yaml"))
            ),
            logic_version_config=str(
                resolve_project_path(
                    os.environ.get("LOGIC_VERSION_CONFIG", "config/strategy_logic_versions.yaml")
                )
            ),
            ledger_path=str(
                resolve_project_path(os.environ.get("LEDGER_PATH", "data/local/ledger.jsonl"))
            ),
            operating_config=str(
                resolve_project_path(os.environ.get("OPERATING_CONFIG", "config/operating.yaml"))
            ),
            cross_venue_config=str(
                resolve_project_path(
                    os.environ.get("CROSS_VENUE_CONFIG", "config/cross_venue.yaml")
                )
            ),
            kalshi_base_url=os.environ.get(
                "KALSHI_BASE_URL", "https://api.elections.kalshi.com/trade-api/v2"
            ).rstrip("/"),
            market_phases_config=str(
                resolve_project_path(
                    os.environ.get("MARKET_PHASES_CONFIG", "config/market_phases.yaml")
                )
            ),
        )


def phase_router_enabled() -> bool:
    return _bool("WC_PHASE_ROUTER_ENABLED", False)


def phase_router_lp_gate() -> bool:
    """When true with router enabled, plan skips LP unless market phase is lp_active."""
    return _bool("WC_PHASE_ROUTER_LP_GATE", False)


def phase_settlement_gate_enabled() -> bool:
    """When true with router enabled, calendar FSM waits for phase settlement."""
    return _bool("WC_PHASE_SETTLEMENT_GATE", True)


def phase_fifa_match_gate_enabled() -> bool:
    """When true with router enabled, block knockout until group fixtures complete."""
    return _bool("WC_FIFA_MATCH_GATE", False)
