"""Runtime configuration from environment (no secrets in repo)."""

from __future__ import annotations

import os
from dataclasses import dataclass


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
            conviction_config=os.environ.get("CONVICTION_CONFIG", "config/conviction.yaml"),
            logic_version_config=os.environ.get(
                "LOGIC_VERSION_CONFIG", "config/strategy_logic_versions.yaml"
            ),
            ledger_path=os.environ.get("LEDGER_PATH", "data/local/ledger.jsonl"),
            operating_config=os.environ.get("OPERATING_CONFIG", "config/operating.yaml"),
        )
