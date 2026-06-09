"""Phase C — auto dual-leg cross-venue arb coordinator."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from world_cup_bot.cross_venue_config import CrossVenueConfig
from world_cup_bot.cross_venue_paper import (
    paper_config_from_cross_venue,
    proposal_from_alert_row,
)
from world_cup_bot.cross_venue_scanner import CrossVenueScanRow
from world_cup_bot.http_client import urlopen_get
from world_cup_bot.kalshi_auth import KalshiAuth, KalshiAuthError, load_kalshi_auth
from world_cup_bot.kalshi_orders import (
    KalshiOrderError,
    KalshiOrderResult,
    build_kalshi_order,
    cancel_order,
    create_limit_order,
)
from world_cup_bot.ledger import LedgerRow, append_row, load_rows
from world_cup_bot.logic_version import StrategyVersionSpec

EXEC_SPEC = StrategyVersionSpec(
    strategy_key="pm_wc_cross_venue_exec",
    version_id="wc_cross_venue_exec_v2",
    deployed_at=datetime(2026, 6, 9, tzinfo=UTC),
    note="Auto dual-leg arb — PM orphan auto-cancel + resolve_orphan_cancel_pm",
    legacy_version_ids=frozenset(),
)

EVENT_EXEC_START = "cross_venue_arb_exec_start"
EVENT_EXEC_LEG = "cross_venue_arb_exec_leg"
EVENT_EXEC_ORPHAN = "cross_venue_arb_exec_orphan"
EVENT_EXEC_COMPLETE = "cross_venue_arb_exec_complete"
EVENT_EXEC_ABORT = "cross_venue_arb_exec_abort"


@dataclass(frozen=True)
class AutoArbConfig:
    max_notional_usd: float = 100.0
    max_daily_notional_usd: float = 500.0
    max_open_arbs: int = 3
    kalshi_first: bool = True
    min_fee_adjusted_gap_pp: float = 0.5
    slippage_buffer_pp: float = 0.25
    exec_dedup_interval_sec: float = 3600.0


@dataclass(frozen=True)
class ExecGateResult:
    allowed: bool
    reason: str
    dry_run: bool


@dataclass(frozen=True)
class ExecAttemptResult:
    team: str
    market_type: str
    status: str  # complete | dry_run | orphan | aborted | skipped | blocked | error
    reason: str | None
    dry_run: bool
    correlation_id: str | None = None
    result: DualLegResult | None = None

    @property
    def attempted(self) -> bool:
        return self.status not in {"skipped", "blocked"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "market_type": self.market_type,
            "status": self.status,
            "reason": self.reason,
            "dry_run": self.dry_run,
            "correlation_id": self.correlation_id,
            "result": self.result.to_dict() if self.result else None,
        }


@dataclass(frozen=True)
class DualLegPlan:
    team: str
    market_type: str
    intent_key: str
    notional_usd: float
    pm_leg: str
    kalshi_leg: str
    pm_price: float
    kalshi_price: float
    pm_token_id: str
    pm_condition_id: str
    kalshi_ticker: str
    correlation_id: str
    fee_adjusted_gap_pp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "market_type": self.market_type,
            "intent_key": self.intent_key,
            "notional_usd": self.notional_usd,
            "pm_leg": self.pm_leg,
            "kalshi_leg": self.kalshi_leg,
            "pm_price": self.pm_price,
            "kalshi_price": self.kalshi_price,
            "pm_token_id": self.pm_token_id,
            "pm_condition_id": self.pm_condition_id,
            "kalshi_ticker": self.kalshi_ticker,
            "correlation_id": self.correlation_id,
            "fee_adjusted_gap_pp": self.fee_adjusted_gap_pp,
        }


@dataclass(frozen=True)
class LegFillResult:
    venue: str  # polymarket | kalshi
    order_id: str
    status: str
    dry_run: bool


@dataclass(frozen=True)
class DualLegResult:
    status: str  # complete | orphan | aborted | dry_run
    plan: DualLegPlan | None
    pm_leg: LegFillResult | None
    kalshi_leg: LegFillResult | None
    orphan_venue: str | None
    reason: str | None
    realized_pnl_usd: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan.to_dict() if self.plan else None,
            "pm_leg": None
            if self.pm_leg is None
            else {
                "venue": self.pm_leg.venue,
                "order_id": self.pm_leg.order_id,
                "status": self.pm_leg.status,
                "dry_run": self.pm_leg.dry_run,
            },
            "kalshi_leg": None
            if self.kalshi_leg is None
            else {
                "venue": self.kalshi_leg.venue,
                "order_id": self.kalshi_leg.order_id,
                "status": self.kalshi_leg.status,
                "dry_run": self.kalshi_leg.dry_run,
            },
            "orphan_venue": self.orphan_venue,
            "reason": self.reason,
            "realized_pnl_usd": self.realized_pnl_usd,
        }


class PmArbClient(Protocol):
    def post_arb_order(
        self,
        *,
        token_id: str,
        side: str,
        price: float,
        size_shares: float,
        dry_run: bool,
    ) -> dict[str, Any]: ...

    def cancel_order(self, order_id: str, *, dry_run: bool) -> dict[str, Any]: ...


def auto_arb_from_cross_venue(cfg: CrossVenueConfig) -> AutoArbConfig:
    raw = cfg.auto_arb
    dedup = 3600.0
    if cfg.paper_arb is not None:
        dedup = cfg.paper_arb.dedup_interval_sec
    if raw is None:
        return AutoArbConfig(exec_dedup_interval_sec=dedup)
    return AutoArbConfig(
        max_notional_usd=raw.max_notional_usd,
        max_daily_notional_usd=raw.max_daily_notional_usd,
        max_open_arbs=raw.max_open_arbs,
        kalshi_first=raw.kalshi_first,
        min_fee_adjusted_gap_pp=raw.min_fee_adjusted_gap_pp,
        slippage_buffer_pp=raw.slippage_buffer_pp,
        exec_dedup_interval_sec=dedup,
    )


def cross_venue_exec_ack() -> bool:
    raw = os.environ.get("WC_CROSS_VENUE_EXEC_ACK", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def cross_venue_auto_exec_enabled() -> bool:
    raw = os.environ.get("WC_CROSS_VENUE_AUTO_EXEC", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def check_exec_gates(
    *,
    dry_run: bool,
    force: bool = False,
    test_auth: bool = False,
    settings: Any | None = None,
) -> ExecGateResult:
    """Gate live dual-leg POST — mirror WC_LIVE_PLAN_ACK / WC_MATCH_SHOCK_LIVE_ACK."""
    auto_on = cross_venue_auto_exec_enabled()
    effective_dry = dry_run or not auto_on
    if not auto_on and not force:
        return ExecGateResult(False, "WC_CROSS_VENUE_AUTO_EXEC not set", True)
    if not effective_dry and not cross_venue_exec_ack():
        return ExecGateResult(False, "WC_CROSS_VENUE_EXEC_ACK not set", effective_dry)
    if not effective_dry and settings is not None:
        from world_cup_bot.preflight import run_preflight

        pf = run_preflight(settings, test_auth=test_auth)
        if not pf.ok:
            failed = [c.detail for c in pf.checks if c.status.value == "fail"]
            return ExecGateResult(
                False,
                f"preflight failed: {'; '.join(failed) or 'unknown'}",
                effective_dry,
            )
    return ExecGateResult(True, "ok", effective_dry)


def fetch_pm_token_ids(
    gamma_url: str,
    *,
    slug: str | None = None,
    condition_id: str | None = None,
    opener: Any | None = None,
) -> tuple[str, str, str]:
    """Return (yes_token_id, no_token_id, condition_id)."""
    params: dict[str, str] = {}
    if slug:
        params["slug"] = slug
    elif condition_id:
        params["condition_ids"] = condition_id
    else:
        raise ValueError("slug or condition_id required for PM token lookup")

    qs = urllib.parse.urlencode(params)
    url = f"{gamma_url.rstrip('/')}/markets?{qs}"
    try:
        if opener is not None:
            with opener(url, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
        else:
            with urlopen_get(url, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Gamma token lookup failed: {exc}") from exc

    markets = payload if isinstance(payload, list) else payload.get("markets") or []
    if not markets:
        raise RuntimeError(f"Gamma returned no market for {params}")
    market = markets[0]
    raw_tokens = market.get("clobTokenIds")
    if isinstance(raw_tokens, str):
        tokens = json.loads(raw_tokens)
    else:
        tokens = list(raw_tokens or [])
    if len(tokens) < 2:
        raise RuntimeError("Gamma market missing clobTokenIds")
    cid = str(market.get("conditionId") or condition_id or "")
    return str(tokens[0]), str(tokens[1]), cid


def _aggressive_price(mid: float, leg: str, buffer_pp: float) -> float:
    bump = buffer_pp / 100.0
    leg = leg.upper()
    if leg == "BUY":
        return min(0.99, mid + bump)
    return max(0.01, mid - bump)


def build_dual_leg_plan(
    row: CrossVenueScanRow,
    cfg: CrossVenueConfig,
    auto: AutoArbConfig,
    *,
    gamma_url: str,
    notional_usd: float | None = None,
    correlation_id: str | None = None,
    opener: Any | None = None,
) -> DualLegPlan:

    paper = paper_config_from_cross_venue(cfg)
    proposal = proposal_from_alert_row(row, cfg, paper, notional_usd=notional_usd)
    if proposal is None:
        raise ValueError("row does not qualify for arb execution")

    notional = min(
        notional_usd if notional_usd is not None else auto.max_notional_usd,
        auto.max_notional_usd,
    )
    slippage_headroom_pp = 2 * auto.slippage_buffer_pp
    min_effective_gap_pp = auto.min_fee_adjusted_gap_pp + slippage_headroom_pp
    if proposal.fee_adjusted_gap_pp < min_effective_gap_pp:
        raise ValueError(
            f"fee-adjusted gap {proposal.fee_adjusted_gap_pp:.2f}pp below "
            f"min {min_effective_gap_pp:.2f}pp after slippage headroom "
            f"({auto.min_fee_adjusted_gap_pp:.2f}pp + 2×{auto.slippage_buffer_pp:.2f}pp)"
        )
    if not row.pm_slug and not row.kalshi_ticker:
        raise ValueError("missing pm_slug and kalshi_ticker")

    yes_tok, _no_tok, cid = fetch_pm_token_ids(
        gamma_url,
        slug=row.pm_slug,
        opener=opener,
    )
    pm_leg, kal_leg = proposal.pm_leg, proposal.kalshi_leg
    pm_px = _aggressive_price(float(row.pm_mid or proposal.pm_mid), pm_leg, auto.slippage_buffer_pp)
    kal_px = _aggressive_price(
        float(row.kalshi_mid or proposal.kalshi_mid),
        kal_leg,
        auto.slippage_buffer_pp,
    )
    ts = int(datetime.now(UTC).timestamp())
    cid_corr = correlation_id or f"cv-exec-{proposal.intent_key}-{ts}"
    return DualLegPlan(
        team=proposal.team,
        market_type=proposal.market_type,
        intent_key=proposal.intent_key,
        notional_usd=notional,
        pm_leg=pm_leg,
        kalshi_leg=kal_leg,
        pm_price=round(pm_px, 4),
        kalshi_price=round(kal_px, 4),
        pm_token_id=yes_tok,
        pm_condition_id=cid,
        kalshi_ticker=str(row.kalshi_ticker or proposal.kalshi_ticker or ""),
        correlation_id=cid_corr,
        fee_adjusted_gap_pp=proposal.fee_adjusted_gap_pp,
    )


def _today_exec_notional(rows: list[dict[str, Any]]) -> float:
    """One notional per correlation_id per day — completion rows only."""
    today = datetime.now(UTC).date().isoformat()
    total = 0.0
    seen: set[str] = set()
    for row in rows:
        if row.get("event") != EVENT_EXEC_COMPLETE:
            continue
        ts = str(row.get("timestamp") or "")[:10]
        if ts != today:
            continue
        cid = str(row.get("correlation_id") or "")
        if cid:
            if cid in seen:
                continue
            seen.add(cid)
        total += float(row.get("notional_usd") or 0)
    return total


def _open_orphan_count(rows: list[dict[str, Any]]) -> int:
    orphans = {r.get("correlation_id") for r in rows if r.get("event") == EVENT_EXEC_ORPHAN}
    resolved = {
        r.get("correlation_id")
        for r in rows
        if r.get("event") == EVENT_EXEC_COMPLETE and r.get("orphan_resolved")
    }
    return len({o for o in orphans if o and o not in resolved})


def check_exec_caps(
    rows: list[dict[str, Any]],
    auto: AutoArbConfig,
    *,
    notional_usd: float,
) -> tuple[bool, str]:
    if notional_usd > auto.max_notional_usd:
        return False, f"notional {notional_usd} > max {auto.max_notional_usd}"
    daily = _today_exec_notional(rows)
    if daily + notional_usd > auto.max_daily_notional_usd:
        return False, f"daily cap {daily + notional_usd} > {auto.max_daily_notional_usd}"
    if _open_orphan_count(rows) >= auto.max_open_arbs:
        return False, f"open orphans >= max_open_arbs {auto.max_open_arbs}"
    return True, "ok"


def _pm_size_shares(notional_usd: float, price: float) -> float:
    return max(1.0, round(notional_usd / max(price, 0.01), 2))


def _append_exec_row(path: Path, row: LedgerRow) -> None:
    append_row(path, row)


def execute_dual_leg(
    plan: DualLegPlan,
    *,
    ledger_path: Path,
    kalshi_auth: KalshiAuth | None,
    kalshi_base_url: str,
    pm_client: PmArbClient | None,
    dry_run: bool,
    kalshi_first: bool = True,
    kalshi_place: Callable[..., KalshiOrderResult] | None = None,
    kalshi_cancel: Callable[..., dict[str, Any]] | None = None,
    pm_cancel: Callable[..., dict[str, Any]] | None = None,
) -> DualLegResult:
    now = datetime.now(UTC).isoformat()
    _append_exec_row(
        ledger_path,
        LedgerRow(
            event=EVENT_EXEC_START,
            logic_version=EXEC_SPEC.version_id,
            strategy_key=EXEC_SPEC.strategy_key,
            timestamp=now,
            team=plan.team,
            notional_usd=plan.notional_usd,
            correlation_id=plan.correlation_id,
            extra=plan.to_dict(),
        ),
    )

    place_kalshi = kalshi_place or (
        lambda req, **kw: create_limit_order(kalshi_auth, req, base_url=kalshi_base_url, **kw)
    )
    cancel_kalshi = kalshi_cancel or (
        lambda oid, **kw: cancel_order(kalshi_auth, oid, base_url=kalshi_base_url, **kw)
    )
    cancel_pm = pm_cancel or (
        (lambda oid, **kw: pm_client.cancel_order(oid, **kw))  # type: ignore[union-attr]
        if pm_client is not None
        else None
    )

    pm_result: LegFillResult | None = None
    kal_result: LegFillResult | None = None

    def _place_pm() -> LegFillResult:
        if pm_client is None:
            raise RuntimeError("PM arb client not configured")
        side = "BUY" if plan.pm_leg == "BUY" else "SELL"
        size = _pm_size_shares(plan.notional_usd, plan.pm_price)
        resp = pm_client.post_arb_order(
            token_id=plan.pm_token_id,
            side=side,
            price=plan.pm_price,
            size_shares=size,
            dry_run=dry_run,
        )
        oid = str(resp.get("orderID") or resp.get("order_id") or f"dry-pm-{plan.pm_token_id[:8]}")
        return LegFillResult(venue="polymarket", order_id=oid, status="submitted", dry_run=dry_run)

    def _place_kalshi() -> LegFillResult:
        if kalshi_auth is None and not dry_run and kalshi_place is None:
            raise KalshiAuthError("Kalshi auth required for live leg")
        req = build_kalshi_order(
            ticker=plan.kalshi_ticker,
            leg=plan.kalshi_leg,
            price=plan.kalshi_price,
            notional_usd=plan.notional_usd,
        )
        res = place_kalshi(req, dry_run=dry_run)
        return LegFillResult(
            venue="kalshi",
            order_id=res.order_id,
            status=res.status,
            dry_run=res.dry_run,
        )

    first, second = ("kalshi", "pm") if kalshi_first else ("pm", "kalshi")
    leg_results: dict[str, LegFillResult] = {}

    try:
        if first == "kalshi":
            leg_results["kalshi"] = _place_kalshi()
            leg_results["pm"] = _place_pm()
        else:
            leg_results["pm"] = _place_pm()
            leg_results["kalshi"] = _place_kalshi()
    except (KalshiOrderError, KalshiAuthError, RuntimeError) as exc:
        filled = leg_results.get(first)
        if filled is not None:
            orphan_venue = filled.venue
            _append_exec_row(
                ledger_path,
                LedgerRow(
                    event=EVENT_EXEC_ORPHAN,
                    logic_version=EXEC_SPEC.version_id,
                    strategy_key=EXEC_SPEC.strategy_key,
                    timestamp=datetime.now(UTC).isoformat(),
                    team=plan.team,
                    notional_usd=plan.notional_usd,
                    correlation_id=plan.correlation_id,
                    reason=str(exc),
                    extra={
                        "orphan_venue": orphan_venue,
                        "filled_order_id": filled.order_id,
                        "intent_key": plan.intent_key,
                    },
                ),
            )
            if filled.order_id and not dry_run:
                if orphan_venue == "kalshi":
                    try:
                        cancel_kalshi(filled.order_id, dry_run=dry_run)
                    except KalshiOrderError:
                        pass
                elif orphan_venue == "polymarket" and cancel_pm is not None:
                    try:
                        cancel_pm(filled.order_id, dry_run=dry_run)
                    except Exception:
                        pass
            pm_result = leg_results.get("pm")
            kal_result = leg_results.get("kalshi")
            return DualLegResult(
                status="orphan",
                plan=plan,
                pm_leg=pm_result,
                kalshi_leg=kal_result,
                orphan_venue=orphan_venue,
                reason=str(exc),
                realized_pnl_usd=None,
            )

        _append_exec_row(
            ledger_path,
            LedgerRow(
                event=EVENT_EXEC_ABORT,
                logic_version=EXEC_SPEC.version_id,
                strategy_key=EXEC_SPEC.strategy_key,
                timestamp=datetime.now(UTC).isoformat(),
                team=plan.team,
                correlation_id=plan.correlation_id,
                reason=str(exc),
            ),
        )
        return DualLegResult(
            status="aborted",
            plan=plan,
            pm_leg=None,
            kalshi_leg=None,
            orphan_venue=None,
            reason=str(exc),
            realized_pnl_usd=None,
        )

    pm_result = leg_results["pm"]
    kal_result = leg_results["kalshi"]
    for leg in (pm_result, kal_result):
        _append_exec_row(
            ledger_path,
            LedgerRow(
                event=EVENT_EXEC_LEG,
                logic_version=EXEC_SPEC.version_id,
                strategy_key=EXEC_SPEC.strategy_key,
                timestamp=datetime.now(UTC).isoformat(),
                team=plan.team,
                notional_usd=plan.notional_usd,
                correlation_id=plan.correlation_id,
                extra={
                    "venue": leg.venue,
                    "order_id": leg.order_id,
                    "status": leg.status,
                    "intent_key": plan.intent_key,
                },
            ),
        )

    realized = None
    if not dry_run:
        # Orders submitted — realized PnL requires venue fill confirmation + reconcile.
        status = "submitted"
    else:
        status = "dry_run"

    _append_exec_row(
        ledger_path,
        LedgerRow(
            event=EVENT_EXEC_COMPLETE,
            logic_version=EXEC_SPEC.version_id,
            strategy_key=EXEC_SPEC.strategy_key,
            timestamp=datetime.now(UTC).isoformat(),
            team=plan.team,
            notional_usd=plan.notional_usd,
            pnl_usd=realized,
            correlation_id=plan.correlation_id,
            extra={
                "intent_key": plan.intent_key,
                "pm_order_id": pm_result.order_id,
                "kalshi_order_id": kal_result.order_id,
                "leg_status": status,
                "pm_status": pm_result.status,
                "kalshi_status": kal_result.status,
            },
        ),
    )
    return DualLegResult(
        status=status,
        plan=plan,
        pm_leg=pm_result,
        kalshi_leg=kal_result,
        orphan_venue=None,
        reason=None,
        realized_pnl_usd=realized,
    )


def list_orphans(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cid: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("event") == EVENT_EXEC_ORPHAN:
            cid = str(row.get("correlation_id") or "")
            if cid:
                by_cid[cid] = row
    for row in rows:
        if row.get("event") == EVENT_EXEC_COMPLETE and row.get("orphan_resolved"):
            cid = str(row.get("correlation_id") or "")
            by_cid.pop(cid, None)
    return list(by_cid.values())


def resolve_orphan_cancel_kalshi(
    orphan_row: dict[str, Any],
    *,
    kalshi_auth: KalshiAuth,
    kalshi_base_url: str,
    ledger_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    order_id = str(orphan_row.get("filled_order_id") or "")
    if not order_id:
        raise ValueError("orphan row missing filled_order_id")
    resp = cancel_order(kalshi_auth, order_id, base_url=kalshi_base_url, dry_run=dry_run)
    append_row(
        ledger_path,
        LedgerRow(
            event=EVENT_EXEC_COMPLETE,
            logic_version=EXEC_SPEC.version_id,
            strategy_key=EXEC_SPEC.strategy_key,
            timestamp=datetime.now(UTC).isoformat(),
            team=orphan_row.get("team"),
            correlation_id=orphan_row.get("correlation_id"),
            reason="orphan_resolved_cancel_kalshi",
            extra={"orphan_resolved": True, "cancel_response": resp},
        ),
    )
    return resp


def resolve_orphan_cancel_pm(
    orphan_row: dict[str, Any],
    *,
    settings: Any,
    ledger_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    from world_cup_bot.clob_live import LiveClobPostError, build_clob_client, cancel_order_id
    from world_cup_bot.config import Settings

    order_id = str(orphan_row.get("filled_order_id") or "")
    if not order_id:
        raise ValueError("orphan row missing filled_order_id")
    if dry_run:
        resp: dict[str, Any] = {"orderID": order_id, "status": "cancel_dry_run"}
    else:
        cfg = settings if isinstance(settings, Settings) else Settings.from_env()
        client = build_clob_client(cfg)
        try:
            resp = cancel_order_id(client, order_id)
        except LiveClobPostError as exc:
            raise RuntimeError(f"PM orphan cancel failed: {exc}") from exc
    append_row(
        ledger_path,
        LedgerRow(
            event=EVENT_EXEC_COMPLETE,
            logic_version=EXEC_SPEC.version_id,
            strategy_key=EXEC_SPEC.strategy_key,
            timestamp=datetime.now(UTC).isoformat(),
            team=orphan_row.get("team"),
            correlation_id=orphan_row.get("correlation_id"),
            reason="orphan_resolved_cancel_pm",
            extra={"orphan_resolved": True, "cancel_response": resp},
        ),
    )
    return resp


def _intent_key(row: CrossVenueScanRow) -> str:
    return f"{row.market_type}:{row.team}"


def _recent_exec_intent_keys(
    rows: list[dict[str, Any]],
    *,
    window_sec: float,
) -> set[str]:
    cutoff = datetime.now(UTC).timestamp() - window_sec
    seen: set[str] = set()
    for row in reversed(rows):
        if row.get("event") not in {
            EVENT_EXEC_START,
            EVENT_EXEC_COMPLETE,
            EVENT_EXEC_ORPHAN,
        }:
            continue
        ts_raw = str(row.get("timestamp") or "")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if ts < cutoff:
            break
        extra = row.get("extra") or row
        key = None
        if isinstance(extra, dict):
            key = extra.get("intent_key")
            if not key and extra.get("team") and extra.get("market_type"):
                key = f"{extra.get('market_type')}:{extra.get('team')}"
        if not key and row.get("team") and isinstance(extra, dict) and extra.get("market_type"):
            key = f"{extra.get('market_type')}:{row.get('team')}"
        elif not key and row.get("team"):
            key = str(row.get("team"))
        if key:
            seen.add(str(key))
    return seen


def attempt_exec_for_row(
    row: CrossVenueScanRow,
    *,
    settings: Any,
    cfg: CrossVenueConfig,
    auto: AutoArbConfig | None = None,
    ledger_path: Path | None = None,
    force: bool = False,
    dry_run: bool | None = None,
    notional: float | None = None,
    test_auth: bool = False,
) -> ExecAttemptResult:
    """Build plan + execute dual-leg for one alert row."""
    auto_cfg = auto or auto_arb_from_cross_venue(cfg)
    path = ledger_path or default_exec_ledger_path()
    rows = load_rows(path)
    intent = _intent_key(row)

    settings_dry = bool(getattr(settings, "dry_run", True))
    base_dry = settings_dry if dry_run is None else dry_run
    gate = check_exec_gates(
        dry_run=base_dry,
        force=force,
        test_auth=test_auth,
        settings=settings,
    )
    if not gate.allowed:
        return ExecAttemptResult(
            team=row.team,
            market_type=row.market_type,
            status="blocked",
            reason=gate.reason,
            dry_run=gate.dry_run,
        )

    effective_dry = gate.dry_run
    if intent in _recent_exec_intent_keys(rows, window_sec=auto_cfg.exec_dedup_interval_sec):
        return ExecAttemptResult(
            team=row.team,
            market_type=row.market_type,
            status="skipped",
            reason=f"dedup window {auto_cfg.exec_dedup_interval_sec:.0f}s",
            dry_run=effective_dry,
        )

    leg_notional = notional if notional is not None else auto_cfg.max_notional_usd
    ok, cap_detail = check_exec_caps(rows, auto_cfg, notional_usd=leg_notional)
    if not ok:
        return ExecAttemptResult(
            team=row.team,
            market_type=row.market_type,
            status="blocked",
            reason=cap_detail,
            dry_run=effective_dry,
        )

    try:
        plan = build_dual_leg_plan(
            row,
            cfg,
            auto_cfg,
            gamma_url=str(getattr(settings, "gamma_url", "")),
            notional_usd=leg_notional,
        )
    except (ValueError, RuntimeError) as exc:
        return ExecAttemptResult(
            team=row.team,
            market_type=row.market_type,
            status="error",
            reason=str(exc),
            dry_run=effective_dry,
        )

    kalshi_auth = None
    pm_client = None
    if not effective_dry:
        from world_cup_bot.clob_live import LivePmArbClient, build_clob_client

        kalshi_auth = load_kalshi_auth()
        pm_client = LivePmArbClient(build_clob_client(settings))

    try:
        result = execute_dual_leg(
            plan,
            ledger_path=path,
            kalshi_auth=kalshi_auth,
            kalshi_base_url=str(getattr(settings, "kalshi_base_url", "")),
            pm_client=pm_client,
            dry_run=effective_dry,
            kalshi_first=auto_cfg.kalshi_first,
        )
    except (KalshiAuthError, KalshiOrderError, RuntimeError) as exc:
        return ExecAttemptResult(
            team=row.team,
            market_type=row.market_type,
            status="error",
            reason=str(exc),
            dry_run=effective_dry,
            correlation_id=plan.correlation_id,
        )

    return ExecAttemptResult(
        team=row.team,
        market_type=row.market_type,
        status=result.status,
        reason=result.reason,
        dry_run=effective_dry,
        correlation_id=plan.correlation_id,
        result=result,
    )


def auto_exec_on_alerts(
    alert_rows: list[CrossVenueScanRow],
    *,
    settings: Any,
    cfg: CrossVenueConfig,
    force: bool = False,
    max_attempts: int = 1,
    notional: float | None = None,
    test_auth: bool = False,
) -> list[ExecAttemptResult]:
    """Attempt dual-leg exec on best alert(s) after a scan cycle."""
    if not alert_rows:
        return []
    if not cross_venue_auto_exec_enabled() and not force:
        return []

    ranked = sorted(
        alert_rows,
        key=lambda r: float(r.gap_pp or 0),
        reverse=True,
    )
    auto = auto_arb_from_cross_venue(cfg)
    out: list[ExecAttemptResult] = []
    for row in ranked[: max(1, max_attempts)]:
        if row.blocked:
            out.append(
                ExecAttemptResult(
                    team=row.team,
                    market_type=row.market_type,
                    status="skipped",
                    reason=row.block_reason or "blocked",
                    dry_run=bool(getattr(settings, "dry_run", True)),
                )
            )
            continue
        attempt = attempt_exec_for_row(
            row,
            settings=settings,
            cfg=cfg,
            auto=auto,
            force=force,
            notional=notional,
            test_auth=test_auth,
        )
        out.append(attempt)
        if attempt.status in {"complete", "dry_run", "orphan"}:
            break
    return out


def default_exec_ledger_path() -> Path:
    rel = os.environ.get(
        "WC_CROSS_VENUE_LEDGER_PATH",
        "data/local/cross_venue_arb_ledger.jsonl",
    )
    from world_cup_bot.paths import resolve_project_path

    return resolve_project_path(rel)
