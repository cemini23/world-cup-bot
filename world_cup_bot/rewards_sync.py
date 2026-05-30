"""Sync Polymarket liquidity rewards into ledger (GET /rewards/user)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from world_cup_bot import ledger
from world_cup_bot.clob_auth import (
    load_clob_auth,
    load_maker_address,
    load_poly_address,
)
from world_cup_bot.clob_rest import fetch_user_rewards_for_date
from world_cup_bot.config import Settings
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.scanner import AdvanceMarket

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class RewardRow:
    earn_date: str
    condition_id: str
    team: str
    rewards_usd: float
    reward_key: str
    asset_address: str
    maker_address: str


@dataclass(frozen=True)
class RewardsSyncResult:
    date: str
    fetched: int
    wc_matched: int
    recorded: int
    skipped_existing: int
    rows: tuple[RewardRow, ...]


def _signature_type_from_env() -> int | None:
    raw = os.environ.get("POLYMARKET_SIGNATURE_TYPE", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def team_by_condition(markets: list[AdvanceMarket]) -> dict[str, str]:
    return {m.condition_id.lower(): m.team for m in markets if m.condition_id}


def parse_reward_rows(
    payload: list[dict],
    *,
    earn_date: str,
    team_map: dict[str, str],
) -> list[RewardRow]:
    out: list[RewardRow] = []
    for row in payload:
        condition_id = str(row.get("condition_id") or "").lower()
        if not condition_id:
            continue
        team = team_map.get(condition_id)
        if not team:
            continue
        earnings = float(row.get("earnings") or 0)
        asset_rate = float(row.get("asset_rate") or 1)
        rewards_usd = round(earnings * asset_rate, 6)
        if rewards_usd <= 0:
            continue
        reward_key = f"{earn_date}:{condition_id}"
        out.append(
            RewardRow(
                earn_date=earn_date,
                condition_id=condition_id,
                team=team,
                rewards_usd=rewards_usd,
                reward_key=reward_key,
                asset_address=str(row.get("asset_address") or ""),
                maker_address=str(row.get("maker_address") or ""),
            )
        )
    return out


def sync_rewards_for_date(
    settings: Settings,
    markets: list[AdvanceMarket],
    version_spec: StrategyVersionSpec,
    *,
    earn_date: str,
    record: bool = False,
    ledger_path: str | None = None,
) -> RewardsSyncResult:
    """Fetch CLOB rewards for one day; optionally append WC rows to ledger."""
    if not _DATE_RE.match(earn_date):
        raise ValueError(f"Invalid date (YYYY-MM-DD): {earn_date}")

    auth = load_clob_auth()
    poly_address = load_poly_address()
    maker_address = load_maker_address()
    payload = fetch_user_rewards_for_date(
        settings.clob_url,
        auth,
        poly_address,
        date=earn_date,
        maker_address=maker_address,
        signature_type=_signature_type_from_env(),
    )

    team_map = team_by_condition(markets)
    rows = parse_reward_rows(payload, earn_date=earn_date, team_map=team_map)
    path = Path(ledger_path or settings.ledger_path)

    recorded = 0
    skipped = 0
    if record:
        for row in rows:
            ok = ledger.record_reward_accrual(
                version_spec,
                path=path,
                team=row.team,
                rewards_usd=row.rewards_usd,
                reward_key=row.reward_key,
                earn_date=row.earn_date,
                condition_id=row.condition_id,
                extra={
                    "asset_address": row.asset_address,
                    "maker_address": row.maker_address,
                    "source": "clob_rewards_user",
                },
            )
            if ok:
                recorded += 1
            else:
                skipped += 1

    return RewardsSyncResult(
        date=earn_date,
        fetched=len(payload),
        wc_matched=len(rows),
        recorded=recorded,
        skipped_existing=skipped,
        rows=tuple(rows),
    )


def default_sync_date(*, offset_days: int = 1) -> str:
    """Yesterday UTC by default — rewards often settle next day."""
    day = datetime.now(UTC).date() - timedelta(days=offset_days)
    return day.isoformat()


def sync_rewards_range(
    settings: Settings,
    markets: list[AdvanceMarket],
    version_spec: StrategyVersionSpec,
    *,
    dates: list[str],
    record: bool = False,
    ledger_path: str | None = None,
) -> list[RewardsSyncResult]:
    results: list[RewardsSyncResult] = []
    for earn_date in dates:
        results.append(
            sync_rewards_for_date(
                settings,
                markets,
                version_spec,
                earn_date=earn_date,
                record=record,
                ledger_path=ledger_path,
            )
        )
    return results


def dates_backfill(*, end: date, days: int) -> list[str]:
    if days < 1:
        return []
    return [(end - timedelta(days=i)).isoformat() for i in range(days)]
