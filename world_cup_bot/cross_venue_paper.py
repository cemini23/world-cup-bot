"""Phase A — paper cross-venue arb ledger (no live POST unless Phase C auto-exec is enabled)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot.cross_venue_config import CrossVenueConfig
from world_cup_bot.cross_venue_scanner import CrossVenueScanResult, CrossVenueScanRow
from world_cup_bot.ledger import LedgerRow, append_row, load_rows
from world_cup_bot.logic_version import StrategyVersionSpec

PAPER_ARB_SPEC = StrategyVersionSpec(
    strategy_key="pm_wc_cross_venue_paper",
    version_id="wc_cross_venue_paper_v1",
    deployed_at=datetime(2026, 5, 30, tzinfo=UTC),
    note="Paper arb intents from cross-venue alerts — no dual-leg execution",
    legacy_version_ids=frozenset(),
)

EVENT_INTENT = "cross_venue_arb_intent_paper"


@dataclass(frozen=True)
class PaperArbConfig:
    default_notional_usd: float = 500.0
    dedup_interval_sec: float = 3600.0
    min_fee_adjusted_gap_pp: float = 0.5


@dataclass(frozen=True)
class PaperArbProposal:
    team: str
    market_type: str
    rules_hash: str
    gap_pp: float
    fee_adjusted_gap_pp: float
    pm_mid: float
    kalshi_mid: float
    pm_leg: str
    kalshi_leg: str
    pm_slug: str | None
    kalshi_ticker: str | None
    notional_usd: float
    theoretical_profit_usd: float
    intent_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "market_type": self.market_type,
            "rules_hash": self.rules_hash,
            "gap_pp": self.gap_pp,
            "fee_adjusted_gap_pp": self.fee_adjusted_gap_pp,
            "pm_mid": self.pm_mid,
            "kalshi_mid": self.kalshi_mid,
            "pm_leg": self.pm_leg,
            "kalshi_leg": self.kalshi_leg,
            "pm_slug": self.pm_slug,
            "kalshi_ticker": self.kalshi_ticker,
            "notional_usd": self.notional_usd,
            "theoretical_profit_usd": self.theoretical_profit_usd,
            "intent_key": self.intent_key,
        }


@dataclass(frozen=True)
class PaperArbRecordResult:
    recorded: int
    skipped_dedup: int
    proposals: tuple[PaperArbProposal, ...]


@dataclass(frozen=True)
class PaperArbPositionRow:
    team: str
    market_type: str
    intent_key: str
    recorded_at: str
    entry_gap_pp: float
    entry_fee_adj_gap_pp: float
    entry_profit_usd: float
    notional_usd: float
    current_gap_pp: float | None
    current_fee_adj_gap_pp: float | None
    current_profit_usd: float | None
    status: str  # open | converged | unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "market_type": self.market_type,
            "intent_key": self.intent_key,
            "recorded_at": self.recorded_at,
            "entry_gap_pp": self.entry_gap_pp,
            "entry_fee_adj_gap_pp": self.entry_fee_adj_gap_pp,
            "entry_profit_usd": self.entry_profit_usd,
            "notional_usd": self.notional_usd,
            "current_gap_pp": self.current_gap_pp,
            "current_fee_adj_gap_pp": self.current_fee_adj_gap_pp,
            "current_profit_usd": self.current_profit_usd,
            "status": self.status,
        }


@dataclass(frozen=True)
class PaperArbPnlSummary:
    logic_version: str
    intent_count: int
    unique_pairs: int
    entry_profit_usd: float
    open_count: int
    converged_count: int
    mtm_profit_usd: float
    positions: tuple[PaperArbPositionRow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "logic_version": self.logic_version,
            "intent_count": self.intent_count,
            "unique_pairs": self.unique_pairs,
            "entry_profit_usd": self.entry_profit_usd,
            "open_count": self.open_count,
            "converged_count": self.converged_count,
            "mtm_profit_usd": self.mtm_profit_usd,
            "positions": [p.to_dict() for p in self.positions],
        }


def default_paper_arb_config() -> PaperArbConfig:
    return PaperArbConfig()


def paper_config_from_cross_venue(cfg: CrossVenueConfig) -> PaperArbConfig:
    slice_cfg = cfg.paper_arb
    if slice_cfg is None:
        return default_paper_arb_config()
    return PaperArbConfig(
        default_notional_usd=slice_cfg.default_notional_usd,
        dedup_interval_sec=slice_cfg.dedup_interval_sec,
        min_fee_adjusted_gap_pp=slice_cfg.min_fee_adjusted_gap_pp,
    )


def load_paper_arb_config(raw: dict[str, Any] | None) -> PaperArbConfig:
    body = raw or {}
    return PaperArbConfig(
        default_notional_usd=float(body.get("default_notional_usd", 500)),
        dedup_interval_sec=float(body.get("dedup_interval_sec", 3600)),
        min_fee_adjusted_gap_pp=float(body.get("min_fee_adjusted_gap_pp", 0.5)),
    )


def default_cross_venue_ledger_path() -> Path:
    from world_cup_bot.paths import resolve_project_path

    rel = os.environ.get(
        "WC_CROSS_VENUE_LEDGER_PATH",
        "data/local/cross_venue_arb_ledger.jsonl",
    )
    return resolve_project_path(rel)


def fee_adjusted_gap_pp(
    gap_pp: float,
    fee_kalshi_profit_pct: float,
    *,
    pm_mid: float | None = None,
    kalshi_mid: float | None = None,
) -> float:
    """Net edge in pp after Kalshi profit fee (K99 hedge model when mids present)."""
    if (
        pm_mid is not None
        and kalshi_mid is not None
        and 0.0 < pm_mid < 1.0
        and 0.0 < kalshi_mid < 1.0
    ):
        hi = max(pm_mid, kalshi_mid)
        fee_drag_pp = (fee_kalshi_profit_pct / 100.0) * hi * 100.0
        return gap_pp - fee_drag_pp
    fee_pp = (fee_kalshi_profit_pct / 100.0) * gap_pp
    return max(0.0, gap_pp - fee_pp)


def _leg_direction(pm_mid: float, kalshi_mid: float) -> tuple[str, str]:
    if pm_mid >= kalshi_mid:
        return "SELL", "BUY"
    return "BUY", "SELL"


def _pair_key(team: str, market_type: str) -> str:
    return f"{market_type}:{team}"


def proposal_from_alert_row(
    row: CrossVenueScanRow,
    config: CrossVenueConfig,
    paper: PaperArbConfig,
    *,
    notional_usd: float | None = None,
) -> PaperArbProposal | None:
    if not row.alert or row.gap_pp is None:
        return None
    if row.pm_mid is None or row.kalshi_mid is None:
        return None

    fee_adj = fee_adjusted_gap_pp(
        row.gap_pp,
        config.fee_kalshi_profit_pct,
        pm_mid=row.pm_mid,
        kalshi_mid=row.kalshi_mid,
    )
    if fee_adj < paper.min_fee_adjusted_gap_pp:
        return None

    notional = notional_usd if notional_usd is not None else paper.default_notional_usd
    profit = round(notional * fee_adj / 100.0, 2)
    pm_leg, kalshi_leg = _leg_direction(row.pm_mid, row.kalshi_mid)
    intent_key = _pair_key(row.team, row.market_type)

    return PaperArbProposal(
        team=row.team,
        market_type=row.market_type,
        rules_hash=row.rules_hash,
        gap_pp=round(row.gap_pp, 2),
        fee_adjusted_gap_pp=round(fee_adj, 2),
        pm_mid=row.pm_mid,
        kalshi_mid=row.kalshi_mid,
        pm_leg=pm_leg,
        kalshi_leg=kalshi_leg,
        pm_slug=row.pm_slug,
        kalshi_ticker=row.kalshi_ticker,
        notional_usd=notional,
        theoretical_profit_usd=profit,
        intent_key=intent_key,
    )


def _parse_ts(ts: str) -> datetime:
    text = ts.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _recent_intent_for_pair(
    rows: list[dict[str, Any]],
    intent_key: str,
    *,
    now: datetime,
    dedup_interval_sec: float,
) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    latest_ts: datetime | None = None
    for row in rows:
        if row.get("event") != EVENT_INTENT:
            continue
        if row.get("intent_key") != intent_key:
            continue
        ts = row.get("timestamp")
        if not ts:
            continue
        dt = _parse_ts(str(ts))
        if latest_ts is None or dt > latest_ts:
            latest_ts = dt
            latest = row
    if latest is None or latest_ts is None:
        return None
    age = (now - latest_ts).total_seconds()
    if age <= dedup_interval_sec:
        return latest
    return None


def should_skip_dedup(
    existing: dict[str, Any] | None,
    proposal: PaperArbProposal,
) -> bool:
    if existing is None:
        return False
    prev_gap = existing.get("gap_pp")
    if prev_gap is None:
        return True
    return abs(float(prev_gap) - proposal.gap_pp) < 0.5


def record_paper_arb_intents(
    result: CrossVenueScanResult,
    config: CrossVenueConfig,
    paper: PaperArbConfig,
    *,
    path: Path,
    correlation_id: str | None = None,
    notional_usd: float | None = None,
    now: datetime | None = None,
) -> PaperArbRecordResult:
    now = now or datetime.now(UTC)
    cid = correlation_id or f"cv-scan-{result.scanned_at}"
    existing = load_rows(path)
    recorded: list[PaperArbProposal] = []
    skipped = 0

    for row in result.alerts:
        proposal = proposal_from_alert_row(
            row,
            config,
            paper,
            notional_usd=notional_usd,
        )
        if proposal is None:
            continue

        recent = _recent_intent_for_pair(
            existing,
            proposal.intent_key,
            now=now,
            dedup_interval_sec=paper.dedup_interval_sec,
        )
        if should_skip_dedup(recent, proposal):
            skipped += 1
            continue

        append_row(
            path,
            LedgerRow(
                event=EVENT_INTENT,
                logic_version=PAPER_ARB_SPEC.version_id,
                strategy_key=PAPER_ARB_SPEC.strategy_key,
                timestamp=now.isoformat(),
                team=proposal.team,
                notional_usd=proposal.notional_usd,
                pnl_usd=proposal.theoretical_profit_usd,
                reason="paper_arb_alert",
                correlation_id=cid,
                extra={
                    **proposal.to_dict(),
                    "scanned_at": result.scanned_at,
                    "alert_threshold_pp": result.alert_threshold_pp,
                    "fee_kalshi_profit_pct": config.fee_kalshi_profit_pct,
                },
            ),
        )
        existing.append(
            {"event": EVENT_INTENT, "intent_key": proposal.intent_key, **proposal.to_dict()}
        )
        recorded.append(proposal)

    return PaperArbRecordResult(
        recorded=len(recorded),
        skipped_dedup=skipped,
        proposals=tuple(recorded),
    )


def _latest_intents_by_pair(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("event") != EVENT_INTENT:
            continue
        if row.get("logic_version") != PAPER_ARB_SPEC.version_id:
            continue
        key = str(
            row.get("intent_key") or _pair_key(str(row.get("team")), str(row.get("market_type")))
        )
        prev = out.get(key)
        if prev is None or str(row.get("timestamp", "")) > str(prev.get("timestamp", "")):
            out[key] = row
    return out


def summarize_paper_arb_pnl(
    rows: list[dict[str, Any]],
    config: CrossVenueConfig,
    paper: PaperArbConfig,
    *,
    scan: CrossVenueScanResult | None = None,
    alert_threshold_pp: float | None = None,
) -> PaperArbPnlSummary:
    threshold = alert_threshold_pp if alert_threshold_pp is not None else config.alert_threshold_pp
    intents = [r for r in rows if r.get("event") == EVENT_INTENT]
    latest = _latest_intents_by_pair(rows)

    gap_by_pair: dict[str, float | None] = {}
    if scan is not None:
        for row in scan.rows:
            gap_by_pair[_pair_key(row.team, row.market_type)] = row.gap_pp

    positions: list[PaperArbPositionRow] = []
    mtm_total = 0.0
    open_count = 0
    converged_count = 0

    for key, entry in sorted(latest.items()):
        entry_gap = float(entry.get("gap_pp") or 0)
        entry_fee_adj = float(entry.get("fee_adjusted_gap_pp") or 0)
        entry_profit = float(entry.get("theoretical_profit_usd") or entry.get("pnl_usd") or 0)
        notional = float(entry.get("notional_usd") or paper.default_notional_usd)
        current_gap = gap_by_pair.get(key)

        current_fee_adj: float | None = None
        current_profit: float | None = None
        status = "unknown"

        if current_gap is not None:
            current_fee_adj = fee_adjusted_gap_pp(current_gap, config.fee_kalshi_profit_pct)
            current_profit = round(notional * current_fee_adj / 100.0, 2)
            if current_gap >= threshold:
                status = "open"
                open_count += 1
                mtm_total += current_profit
            else:
                status = "converged"
                converged_count += 1
                mtm_total += entry_profit
        else:
            mtm_total += entry_profit

        positions.append(
            PaperArbPositionRow(
                team=str(entry.get("team")),
                market_type=str(entry.get("market_type")),
                intent_key=key,
                recorded_at=str(entry.get("timestamp") or ""),
                entry_gap_pp=entry_gap,
                entry_fee_adj_gap_pp=entry_fee_adj,
                entry_profit_usd=entry_profit,
                notional_usd=notional,
                current_gap_pp=current_gap,
                current_fee_adj_gap_pp=current_fee_adj,
                current_profit_usd=current_profit,
                status=status,
            )
        )

    entry_total = sum(
        float(r.get("theoretical_profit_usd") or r.get("pnl_usd") or 0) for r in intents
    )

    return PaperArbPnlSummary(
        logic_version=PAPER_ARB_SPEC.version_id,
        intent_count=len(intents),
        unique_pairs=len(latest),
        entry_profit_usd=round(entry_total, 2),
        open_count=open_count,
        converged_count=converged_count,
        mtm_profit_usd=round(mtm_total, 2),
        positions=tuple(positions),
    )
