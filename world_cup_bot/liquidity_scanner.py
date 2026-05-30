"""CLOB order-book depth scan — replaces manual human_review depth checks (K84+)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from world_cup_bot.clob_rest import fetch_book
from world_cup_bot.operating_config import BilateralOps, LiquidityOps, OperatingConfig
from world_cup_bot.scanner import AdvanceMarket

Side = Literal["bid", "ask"]


@dataclass(frozen=True)
class BookSideDepth:
    token_id: str
    label: str  # e.g. "YES" / "NO"
    side: Side
    levels: int
    depth_usd: float
    depth_in_band_usd: float


@dataclass(frozen=True)
class TokenBookDepth:
    token_id: str
    label: str
    bid: BookSideDepth
    ask: BookSideDepth
    best_bid: float | None
    best_ask: float | None

    @property
    def min_band_depth_usd(self) -> float:
        return min(self.bid.depth_in_band_usd, self.ask.depth_in_band_usd)


@dataclass(frozen=True)
class LiquidityReport:
    market: AdvanceMarket
    midpoint: float
    half_spread: float
    yes: TokenBookDepth | None
    no: TokenBookDepth | None
    fetch_errors: tuple[str, ...]
    passes: bool
    reasons: tuple[str, ...]

    @property
    def min_band_depth_usd(self) -> float | None:
        depths: list[float] = []
        if self.yes:
            depths.append(self.yes.min_band_depth_usd)
        if self.no:
            depths.append(self.no.min_band_depth_usd)
        return min(depths) if depths else None

    @property
    def gamma_liquidity(self) -> float | None:
        return self.market.liquidity


def _parse_levels(raw: list[Any] | None) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        try:
            out.append((float(row["price"]), float(row["size"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _depth_usd(levels: list[tuple[float, float]]) -> float:
    return sum(price * size for price, size in levels)


def _depth_in_band(
    levels: list[tuple[float, float]],
    *,
    side: Side,
    mid: float,
    half_spread: float,
) -> float:
    lo = mid - half_spread
    hi = mid + half_spread
    total = 0.0
    for price, size in levels:
        if side == "bid" and lo <= price <= hi:
            total += price * size
        elif side == "ask" and lo <= price <= hi:
            total += price * size
    return total


def _token_depth(
    book: dict[str, Any],
    *,
    token_id: str,
    label: str,
    mid: float,
    half_spread: float,
) -> TokenBookDepth:
    bids = _parse_levels(book.get("bids"))
    asks = _parse_levels(book.get("asks"))
    bid_depth = BookSideDepth(
        token_id=token_id,
        label=label,
        side="bid",
        levels=len(bids),
        depth_usd=_depth_usd(bids),
        depth_in_band_usd=_depth_in_band(bids, side="bid", mid=mid, half_spread=half_spread),
    )
    ask_depth = BookSideDepth(
        token_id=token_id,
        label=label,
        side="ask",
        levels=len(asks),
        depth_usd=_depth_usd(asks),
        depth_in_band_usd=_depth_in_band(asks, side="ask", mid=mid, half_spread=half_spread),
    )
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    return TokenBookDepth(
        token_id=token_id,
        label=label,
        bid=bid_depth,
        ask=ask_depth,
        best_bid=best_bid,
        best_ask=best_ask,
    )


def _half_spread_cents(market: AdvanceMarket, cfg: LiquidityOps) -> float:
    if cfg.max_spread_cents is not None:
        return cfg.max_spread_cents / 100.0
    if market.rewards_max_spread is not None:
        return market.rewards_max_spread / 100.0
    return 0.045


def _needs_bilateral_book(
    market: AdvanceMarket,
    *,
    bilateral: BilateralOps | None = None,
) -> bool:
    mid = market.mid
    if mid is None:
        return False
    high = bilateral.high_mid if bilateral else 0.90
    low = bilateral.low_mid if bilateral else 0.10
    return market.bilateral_mode or mid >= high or mid <= low


def ahead_bid_notional_usd(book: dict[str, Any], fill_price: float) -> float:
    """USD on bids strictly better than fill price — queue-ahead proxy for depletion."""
    bids = _parse_levels(book.get("bids"))
    return sum(price * size for price, size in bids if price > fill_price)


def fetch_ahead_bid_notional_usd(
    clob_url: str,
    token_id: str,
    fill_price: float,
) -> float:
    book = fetch_book(clob_url, token_id)
    return ahead_bid_notional_usd(book, fill_price)


def evaluate_liquidity_gate(
    *,
    yes: TokenBookDepth | None,
    no: TokenBookDepth | None,
    cfg: LiquidityOps,
    bilateral: bool,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if yes is None:
        return False, ("YES book missing",)

    checks: list[tuple[str, TokenBookDepth]] = [("YES", yes)]
    if bilateral:
        if no is None:
            return False, ("NO book required for bilateral/high-mid market",)
        checks.append(("NO", no))

    for label, tok in checks:
        if tok.bid.levels < cfg.min_levels_per_side:
            reasons.append(f"{label} bid levels {tok.bid.levels} < {cfg.min_levels_per_side}")
        if tok.ask.levels < cfg.min_levels_per_side:
            reasons.append(f"{label} ask levels {tok.ask.levels} < {cfg.min_levels_per_side}")
        if tok.bid.depth_in_band_usd < cfg.min_depth_within_reward_spread_usd:
            reasons.append(
                f"{label} bid band depth ${tok.bid.depth_in_band_usd:.0f} "
                f"< ${cfg.min_depth_within_reward_spread_usd:.0f}"
            )
        if tok.ask.depth_in_band_usd < cfg.min_ask_depth_within_reward_spread_usd:
            reasons.append(
                f"{label} ask band depth ${tok.ask.depth_in_band_usd:.0f} "
                f"< ${cfg.min_ask_depth_within_reward_spread_usd:.0f}"
            )

    combined = 0.0
    if yes:
        combined += yes.bid.depth_usd + yes.ask.depth_usd
    if no:
        combined += no.bid.depth_usd + no.ask.depth_usd
    if combined < cfg.min_combined_book_depth_usd:
        reasons.append(
            f"combined book depth ${combined:.0f} < ${cfg.min_combined_book_depth_usd:.0f}"
        )

    if reasons:
        return False, tuple(reasons)
    return True, ("liquidity gate pass",)


def scan_market_liquidity(
    market: AdvanceMarket,
    *,
    clob_url: str,
    cfg: LiquidityOps,
    bilateral: BilateralOps | None = None,
) -> LiquidityReport:
    errors: list[str] = []
    mid = market.mid
    if mid is None:
        return LiquidityReport(
            market=market,
            midpoint=0.0,
            half_spread=0.0,
            yes=None,
            no=None,
            fetch_errors=("no midpoint from Gamma",),
            passes=False,
            reasons=("no midpoint",),
        )

    half = _half_spread_cents(market, cfg)
    needs_bilateral = _needs_bilateral_book(market, bilateral=bilateral)

    yes_book: dict[str, Any] | None = None
    no_book: dict[str, Any] | None = None

    try:
        yes_book = fetch_book(clob_url, market.yes_token_id)
    except Exception as exc:  # noqa: BLE001 — surface fetch errors in report
        errors.append(f"YES book: {exc}")

    if needs_bilateral:
        try:
            no_book = fetch_book(clob_url, market.no_token_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"NO book: {exc}")

    yes_depth = (
        _token_depth(
            yes_book,
            token_id=market.yes_token_id,
            label="YES",
            mid=mid,
            half_spread=half,
        )
        if yes_book
        else None
    )
    no_depth = (
        _token_depth(
            no_book,
            token_id=market.no_token_id,
            label="NO",
            mid=1.0 - mid,
            half_spread=half,
        )
        if no_book
        else None
    )

    if errors:
        return LiquidityReport(
            market=market,
            midpoint=mid,
            half_spread=half,
            yes=yes_depth,
            no=no_depth,
            fetch_errors=tuple(errors),
            passes=False,
            reasons=tuple(errors),
        )

    passed, reasons = evaluate_liquidity_gate(
        yes=yes_depth,
        no=no_depth,
        cfg=cfg,
        bilateral=needs_bilateral,
    )
    return LiquidityReport(
        market=market,
        midpoint=mid,
        half_spread=half,
        yes=yes_depth,
        no=no_depth,
        fetch_errors=(),
        passes=passed,
        reasons=reasons,
    )


def scan_markets_liquidity(
    markets: list[AdvanceMarket],
    *,
    clob_url: str,
    cfg: LiquidityOps,
    teams: set[str] | None = None,
    bilateral: BilateralOps | None = None,
) -> list[LiquidityReport]:
    out: list[LiquidityReport] = []
    for m in markets:
        if teams and m.team not in teams and not any(t.lower() == m.team.lower() for t in teams):
            continue
        out.append(scan_market_liquidity(m, clob_url=clob_url, cfg=cfg, bilateral=bilateral))
    return out


def liquidity_map_for_markets(
    markets: list[AdvanceMarket],
    *,
    clob_url: str,
    operating: OperatingConfig,
    teams: set[str] | None = None,
) -> tuple[LiquidityOps, dict[str, LiquidityReport]]:
    cfg = operating.liquidity
    reports = scan_markets_liquidity(
        markets,
        clob_url=clob_url,
        cfg=cfg,
        teams=teams,
        bilateral=operating.bilateral,
    )
    return cfg, {r.market.team: r for r in reports}


def report_to_dict(report: LiquidityReport) -> dict[str, Any]:
    def _tok(t: TokenBookDepth | None) -> dict[str, Any] | None:
        if t is None:
            return None
        return {
            "token_id": t.token_id,
            "label": t.label,
            "best_bid": t.best_bid,
            "best_ask": t.best_ask,
            "bid_levels": t.bid.levels,
            "ask_levels": t.ask.levels,
            "bid_depth_usd": round(t.bid.depth_usd, 2),
            "ask_depth_usd": round(t.ask.depth_usd, 2),
            "bid_band_usd": round(t.bid.depth_in_band_usd, 2),
            "ask_band_usd": round(t.ask.depth_in_band_usd, 2),
            "min_band_usd": round(t.min_band_depth_usd, 2),
        }

    return {
        "team": report.market.team,
        "mid": report.midpoint,
        "half_spread": report.half_spread,
        "gamma_liquidity": report.gamma_liquidity,
        "passes": report.passes,
        "reasons": list(report.reasons),
        "fetch_errors": list(report.fetch_errors),
        "yes": _tok(report.yes),
        "no": _tok(report.no),
    }


def reports_to_json(reports: list[LiquidityReport]) -> str:
    return json.dumps([report_to_dict(r) for r in reports], indent=2)
