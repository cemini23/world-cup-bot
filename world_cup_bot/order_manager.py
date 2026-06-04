"""Open-order fetch, calendar cancel, cancel-replace, and trading halt (go-live safety)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from world_cup_bot import calendar_guard
from world_cup_bot.clob_auth import ClobAuth, MissingClobAuthError, load_clob_auth, load_poly_address
from world_cup_bot.clob_rest import fetch_open_orders
from world_cup_bot.config import Settings
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.quoter import QuoteIntent
from world_cup_bot.scanner import AdvanceMarket

logger = logging.getLogger(__name__)

OPEN_STATUSES = frozenset({"LIVE", "OPEN", "ACTIVE"})


@dataclass(frozen=True)
class OpenOrder:
    order_id: str
    asset_id: str
    condition_id: str
    side: str
    price: float
    size: float
    status: str
    team: str | None = None

    @classmethod
    def from_clob_row(
        cls,
        row: dict,
        *,
        team_by_asset: dict[str, str] | None = None,
    ) -> OpenOrder | None:
        order_id = str(row.get("id") or row.get("order_id") or "").strip()
        asset_id = str(row.get("asset_id") or row.get("token_id") or "").strip()
        if not order_id or not asset_id:
            return None
        status = str(row.get("status") or row.get("order_status") or "LIVE").upper()
        if status not in OPEN_STATUSES:
            return None
        try:
            price = float(row.get("price") or 0)
            original = float(row.get("original_size") or row.get("size") or 0)
            matched = float(row.get("size_matched") or 0)
            size = max(0.0, original - matched)
        except (TypeError, ValueError):
            return None
        if size <= 0:
            return None
        team = None
        if team_by_asset:
            team = team_by_asset.get(asset_id)
        return cls(
            order_id=order_id,
            asset_id=asset_id,
            condition_id=str(row.get("market") or row.get("condition_id") or ""),
            side=str(row.get("side") or "BUY").upper(),
            price=price,
            size=size,
            status=status,
            team=team,
        )


@dataclass
class TradingHalt:
    """In-memory halt — stops new quotes for team(s) after kill switch or operator action."""

    global_halt: bool = False
    halted_teams: set[str] = field(default_factory=set)
    reason: str = ""

    def is_halted(self, team: str) -> bool:
        return self.global_halt or team in self.halted_teams

    def halt_team(self, team: str, reason: str) -> None:
        self.halted_teams.add(team)
        self.reason = reason
        logger.warning("TRADING_HALT team=%s — %s", team, reason)

    def halt_all(self, reason: str) -> None:
        self.global_halt = True
        self.reason = reason
        logger.warning("TRADING_HALT global — %s", reason)


@dataclass(frozen=True)
class CancelResult:
    order_ids: list[str]
    dry_run: bool
    reason: str
    teams: tuple[str, ...] = ()


def build_wc_index(
    markets: list[AdvanceMarket],
) -> tuple[set[str], set[str], dict[str, str], dict[str, AdvanceMarket]]:
    """Token ids, condition ids, asset→team, condition→market."""
    token_ids: set[str] = set()
    condition_ids: set[str] = set()
    team_by_asset: dict[str, str] = {}
    market_by_condition: dict[str, AdvanceMarket] = {}
    for m in markets:
        if m.yes_token_id:
            token_ids.add(m.yes_token_id)
            team_by_asset[m.yes_token_id] = m.team
        if m.no_token_id:
            token_ids.add(m.no_token_id)
            team_by_asset[m.no_token_id] = m.team
        if m.condition_id:
            condition_ids.add(m.condition_id)
            market_by_condition[m.condition_id] = m
    return token_ids, condition_ids, team_by_asset, market_by_condition


def _skip_open_orders_fetch_without_l2(settings: Settings, auth: ClobAuth | None) -> bool:
    """DRY_RUN shadow plan on US monitor — no L2 creds; treat as zero open orders."""
    if auth is not None or not settings.dry_run:
        return False
    try:
        load_clob_auth()
    except MissingClobAuthError:
        return True
    return False


def fetch_wc_open_orders(
    settings: Settings,
    markets: list[AdvanceMarket],
    *,
    auth: ClobAuth | None = None,
    address: str | None = None,
) -> list[OpenOrder]:
    """Open CLOB orders limited to WC advance market token ids."""
    token_ids, _, team_by_asset, _ = build_wc_index(markets)
    if not token_ids:
        return []
    if _skip_open_orders_fetch_without_l2(settings, auth):
        logger.info("SKIP fetch open orders (DRY_RUN, no L2 creds)")
        return []
    auth = auth or load_clob_auth()
    address = address or load_poly_address()

    raw = fetch_open_orders(settings.clob_url, auth, address)
    out: list[OpenOrder] = []
    for row in raw:
        parsed = OpenOrder.from_clob_row(row, team_by_asset=team_by_asset)
        if parsed and parsed.asset_id in token_ids:
            out.append(parsed)
    return out


def _cancel_order_ids(settings: Settings, order_ids: list[str], *, dry_run: bool) -> list[str]:
    if not order_ids:
        return []
    if dry_run:
        for oid in order_ids:
            logger.info("CANCEL_DRY order_id=%s", oid)
        return order_ids

    from world_cup_bot.clob_live import LiveClobPostError, build_clob_client, cancel_order_ids

    client = build_clob_client(settings)
    try:
        cancel_order_ids(client, order_ids)
    except LiveClobPostError as exc:
        raise RuntimeError(f"cancel failed: {exc}") from exc
    for oid in order_ids:
        logger.info("CANCEL order_id=%s", oid)
    return order_ids


def cancel_orders(
    settings: Settings,
    orders: list[OpenOrder],
    *,
    reason: str,
    dry_run: bool | None = None,
    ledger_path: str | None = None,
    version_spec: StrategyVersionSpec | None = None,
) -> CancelResult:
    """Cancel explicit open orders."""
    dry = settings.dry_run if dry_run is None else dry_run
    ids = [o.order_id for o in orders]
    teams = tuple(sorted({o.team for o in orders if o.team}))
    _cancel_order_ids(settings, ids, dry_run=dry)
    result = CancelResult(order_ids=ids, dry_run=dry, reason=reason, teams=teams)
    _maybe_record_cancel(result, ledger_path, version_spec)
    _maybe_notify_cancel(result)
    return result


def _maybe_record_cancel(
    result: CancelResult,
    ledger_path: str | None,
    version_spec: StrategyVersionSpec | None,
) -> None:
    if not result.order_ids or not ledger_path or version_spec is None:
        return
    from pathlib import Path

    from world_cup_bot import ledger

    ledger.record_order_cancel(
        version_spec,
        path=Path(ledger_path),
        order_ids=result.order_ids,
        reason=result.reason,
        teams=result.teams,
        dry_run=result.dry_run,
    )


def _maybe_notify_cancel(result: CancelResult) -> None:
    if not result.order_ids:
        return
    from world_cup_bot.alerts import notify

    teams = ", ".join(result.teams) if result.teams else "?"
    notify(
        "order_cancel",
        f"Cancelled {len(result.order_ids)} WC order(s) — {result.reason}",
        extra={
            "teams": list(result.teams),
            "dry_run": result.dry_run,
            "count": len(result.order_ids),
        },
    )
    if "kill_switch" in result.reason:
        notify(
            "trading_halt",
            f"Trading halt pull — {teams}",
            extra={"reason": result.reason, "teams": list(result.teams)},
        )


def cancel_for_teams(
    settings: Settings,
    markets: list[AdvanceMarket],
    teams: set[str],
    *,
    reason: str,
    dry_run: bool | None = None,
    ledger_path: str | None = None,
    version_spec: StrategyVersionSpec | None = None,
) -> CancelResult:
    """Cancel all open WC orders for the given teams."""
    if not teams:
        return CancelResult(order_ids=[], dry_run=settings.dry_run, reason=reason)
    open_orders = fetch_wc_open_orders(settings, markets)
    targets = [o for o in open_orders if o.team and o.team in teams]
    return cancel_orders(
        settings,
        targets,
        reason=reason,
        dry_run=dry_run,
        ledger_path=ledger_path,
        version_spec=version_spec,
    )


def cancel_for_cancel_window(
    settings: Settings,
    markets: list[AdvanceMarket],
    *,
    min_hours: float | None = None,
    reason: str = "calendar cancel window",
    dry_run: bool | None = None,
    ledger_path: str | None = None,
    version_spec: StrategyVersionSpec | None = None,
) -> CancelResult:
    """Cancel open orders for every team inside the pre-kickoff cancel window."""
    threshold = min_hours if min_hours is not None else settings.min_hours_before_kickoff
    rows = calendar_guard.teams_in_cancel_window(min_hours_before_kickoff=threshold)
    teams = {team for team, _ in rows}
    if not teams:
        return CancelResult(order_ids=[], dry_run=settings.dry_run, reason=reason, teams=())
    detail = f"{reason} — teams: {', '.join(sorted(teams))}"
    return cancel_for_teams(
        settings,
        markets,
        teams,
        reason=detail,
        dry_run=dry_run,
        ledger_path=ledger_path,
        version_spec=version_spec,
    )


def cancel_all_wc_orders(
    settings: Settings,
    markets: list[AdvanceMarket],
    *,
    reason: str = "cancel all WC advance orders",
    dry_run: bool | None = None,
    ledger_path: str | None = None,
    version_spec: StrategyVersionSpec | None = None,
) -> CancelResult:
    open_orders = fetch_wc_open_orders(settings, markets)
    return cancel_orders(
        settings,
        open_orders,
        reason=reason,
        dry_run=dry_run,
        ledger_path=ledger_path,
        version_spec=version_spec,
    )


def cancel_open_orders_for_assets(
    settings: Settings,
    markets: list[AdvanceMarket],
    asset_ids: set[str],
    *,
    reason: str = "cancel-replace before new quote",
    dry_run: bool | None = None,
) -> CancelResult:
    """Cancel open orders on specific token ids (cancel-replace path)."""
    if not asset_ids:
        return CancelResult(order_ids=[], dry_run=settings.dry_run, reason=reason)
    open_orders = fetch_wc_open_orders(settings, markets)
    targets = [o for o in open_orders if o.asset_id in asset_ids]
    return cancel_orders(settings, targets, reason=reason, dry_run=dry_run)


def cancel_replace_before_submit(
    settings: Settings,
    markets: list[AdvanceMarket],
    intents: list[QuoteIntent],
    *,
    price_tolerance: float = 0.005,
    dry_run: bool | None = None,
    ledger_path: str | None = None,
    version_spec: StrategyVersionSpec | None = None,
) -> list[CancelResult]:
    """Cancel stale resting quotes before posting new intents (same asset, price drift)."""
    if not intents:
        return []
    open_orders = fetch_wc_open_orders(settings, markets)
    by_asset: dict[str, list[OpenOrder]] = {}
    for o in open_orders:
        by_asset.setdefault(o.asset_id, []).append(o)

    results: list[CancelResult] = []
    for intent in intents:
        existing = by_asset.get(intent.token_id, [])
        stale = [
            o for o in existing if o.side == "BUY" and abs(o.price - intent.price) > price_tolerance
        ]
        if stale:
            results.append(
                cancel_orders(
                    settings,
                    stale,
                    reason=f"cancel-replace stale {intent.team} {intent.side}",
                    dry_run=dry_run,
                    ledger_path=ledger_path,
                    version_spec=version_spec,
                )
            )
        # Always cancel same-price duplicates before post to avoid double exposure
        dupes = [
            o
            for o in existing
            if o.side == "BUY" and abs(o.price - intent.price) <= price_tolerance
        ]
        if dupes:
            results.append(
                cancel_orders(
                    settings,
                    dupes,
                    reason=f"cancel-replace refresh {intent.team} {intent.side}",
                    dry_run=dry_run,
                    ledger_path=ledger_path,
                    version_spec=version_spec,
                )
            )
    return results


def apply_fill_safety_actions(
    settings: Settings,
    markets: list[AdvanceMarket],
    *,
    team: str,
    kill_switch: bool,
    pull_quotes: bool,
    halt: TradingHalt | None = None,
    dry_run: bool | None = None,
    ledger_path: str | None = None,
    version_spec: StrategyVersionSpec | None = None,
) -> CancelResult | None:
    """Kill switch / queue pull → cancel resting quotes and optionally halt team."""
    if not kill_switch and not pull_quotes:
        return None
    if kill_switch and halt is not None:
        halt.halt_team(team, "kill_switch — fill inside cancel/live window")
    result = cancel_for_teams(
        settings,
        markets,
        {team},
        reason="kill_switch" if kill_switch else "queue_depletion pull",
        dry_run=dry_run,
        ledger_path=ledger_path,
        version_spec=version_spec,
    )
    return result


def format_orders_table(orders: list[OpenOrder]) -> str:
    if not orders:
        return "No open WC advance orders."
    lines = [f"{'TEAM':20} {'SIDE':>4} {'PRICE':>6} {'SIZE':>8}  ORDER_ID"]
    for o in sorted(orders, key=lambda x: (x.team or "", x.asset_id)):
        lines.append(
            f"{(o.team or '?'):20} {o.side:>4} {o.price:>6.2f} {o.size:>8.1f}  {o.order_id[:24]}"
        )
    return "\n".join(lines)
