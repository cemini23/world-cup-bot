"""Shared shock tape JSONL parsing and shock scan (Module 8)."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from world_cup_bot.match_shock import (
    BookLevel,
    PriceTick,
    ShockContext,
    bucket_passes_backtest_filter,
    detect_shock,
    plan_ladder,
    slug_in_scope,
)
from world_cup_bot.match_shock_config import MatchShockConfig

TICK_PRICE_SANE_MIN = 0.02
TICK_PRICE_SANE_MAX = 0.98


_KICKOFF_SLUG_DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})-")


def shock_tape_tz() -> ZoneInfo:
    """WC match slugs use US calendar dates — default Eastern, not UTC."""
    name = os.environ.get("WC_MATCH_SHOCK_TAPE_TZ", "America/New_York").strip()
    return ZoneInfo(name)


def shock_tape_calendar_day(now: datetime | None = None) -> str:
    tz = shock_tape_tz()
    dt = now if now is not None else datetime.now(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)
    return dt.strftime("%Y-%m-%d")


def tape_path_for_day(tape_dir: Path, day: str) -> Path:
    return tape_dir / f"{day}.jsonl"


def kickoff_slug_dates(kickoff_json: Path) -> list[str]:
    """Extract YYYY-MM-DD segments from fifwc kickoff slugs (match calendar day)."""
    try:
        payload = json.loads(kickoff_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    dates: list[str] = []
    seen: set[str] = set()
    for row in payload.get("markets") or []:
        slug = str(row.get("slug") or "")
        m = _KICKOFF_SLUG_DATE_RE.search(slug)
        if not m:
            continue
        d = m.group(1)
        if d not in seen:
            seen.add(d)
            dates.append(d)
    return sorted(dates)


def resolve_shock_tape_path(
    tape_dir: Path,
    *,
    kickoff_json: Path | None = None,
) -> Path | None:
    """Resolve daily tape: TZ calendar day, kickoff slug dates, then prior TZ day."""
    day = shock_tape_calendar_day()
    candidate = tape_path_for_day(tape_dir, day)
    if candidate.is_file():
        return candidate

    if kickoff_json is not None and kickoff_json.is_file():
        for slug_day in reversed(kickoff_slug_dates(kickoff_json)):
            path = tape_path_for_day(tape_dir, slug_day)
            if path.is_file():
                return path

    tz = shock_tape_tz()
    today = datetime.now(tz).date()
    prior = today.fromordinal(today.toordinal() - 1)
    prior_path = tape_path_for_day(tape_dir, prior.isoformat())
    if prior_path.is_file():
        return prior_path
    return None


@dataclass
class ParsedTick:
    ts_ms: int
    price: float
    slug: str
    elapsed_ms: int
    goal_diff: int
    bids: tuple[BookLevel, ...]


def parse_tick_line(raw: dict) -> ParsedTick | None:
    try:
        ts_ms = int(raw["ts_ms"])
        price = float(raw["price"])
        slug = str(raw["slug"])
    except (KeyError, TypeError, ValueError):
        return None
    elapsed_ms = int(raw.get("elapsed_ms") or 0)
    goal_diff = int(raw.get("goal_diff") or 0)
    bids_raw = raw.get("bids") or []
    bids: list[BookLevel] = []
    for row in bids_raw:
        try:
            bids.append(BookLevel(price=float(row["price"]), size=float(row["size"])))
        except (KeyError, TypeError, ValueError):
            continue
    return ParsedTick(
        ts_ms=ts_ms,
        price=price,
        slug=slug,
        elapsed_ms=elapsed_ms,
        goal_diff=goal_diff,
        bids=tuple(bids),
    )


def load_ticks(path: Path) -> list[ParsedTick]:
    ticks: list[ParsedTick] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            tick = parse_tick_line(raw)
            if tick is not None:
                ticks.append(tick)
    return ticks


def load_ticks_for_slugs(
    path: Path,
    slug_set: frozenset[str] | set[str] | None,
) -> list[ParsedTick]:
    """Stream JSONL tape — only retain ticks for requested slugs (low RAM on large tapes)."""
    if not slug_set:
        return load_ticks(path)
    wanted = frozenset(slug_set)
    ticks: list[ParsedTick] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            slug = str(raw.get("slug") or "")
            if slug not in wanted:
                continue
            tick = parse_tick_line(raw)
            if tick is not None:
                ticks.append(tick)
    return ticks


def slugs_in_tape(path: Path) -> list[str]:
    """Unique slugs in a tape file without loading ticks into RAM."""
    seen: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            slug = str(raw.get("slug") or "")
            if slug:
                seen.add(slug)
    return sorted(seen)


def load_ticks_for_slug(path: Path, slug: str) -> list[ParsedTick]:
    """Stream JSONL tape for a single slug (one slug in RAM — egress-safe)."""
    ticks: list[ParsedTick] = []
    want = str(slug)
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            if str(raw.get("slug") or "") != want:
                continue
            tick = parse_tick_line(raw)
            if tick is not None:
                ticks.append(tick)
    return ticks


def group_by_slug(ticks: list[ParsedTick]) -> dict[str, list[ParsedTick]]:
    out: dict[str, list[ParsedTick]] = defaultdict(list)
    for t in ticks:
        out[t.slug].append(t)
    for slug in out:
        out[slug].sort(key=lambda x: x.ts_ms)
    return dict(out)


def scan_shocks(
    ticks: list[ParsedTick],
    cfg: MatchShockConfig,
) -> list[tuple[ParsedTick, ShockContext, float]]:
    """Return (trigger_tick, context, depth_cents) for each detected shock."""
    det = cfg.detection
    window_ms = det.window_ms
    cooldown_ms = det.cooldown_ms
    results: list[tuple[ParsedTick, ShockContext, float]] = []
    last_shock_ts: int | None = None

    for i, tick in enumerate(ticks):
        if not slug_in_scope(tick.slug, cfg):
            continue
        if tick.price < TICK_PRICE_SANE_MIN or tick.price > TICK_PRICE_SANE_MAX:
            continue
        window_start = tick.ts_ms - window_ms
        window = [
            PriceTick(ts_ms=t.ts_ms, price=t.price)
            for t in ticks[: i + 1]
            if t.ts_ms >= window_start and TICK_PRICE_SANE_MIN <= t.price <= TICK_PRICE_SANE_MAX
        ]
        shock = detect_shock(
            tuple(window),
            min_drop_pct=det.min_drop_pct,
            min_drop_abs=det.min_drop_abs,
        )
        if not shock.shock or shock.pre_price is None or shock.depth is None:
            continue
        if last_shock_ts is not None and tick.ts_ms - last_shock_ts < cooldown_ms:
            continue
        ctx = ShockContext(
            slug=tick.slug,
            pre_price=shock.pre_price,
            bids=tick.bids,
            elapsed_ms=tick.elapsed_ms,
            goal_diff=tick.goal_diff,
        )
        results.append((tick, ctx, shock.depth * 100.0))
        last_shock_ts = tick.ts_ms
    return results


def build_distributions(
    shocks: list[tuple[ParsedTick, ShockContext, float]],
    cfg: MatchShockConfig,
) -> dict[str, list[float]]:
    depths: dict[str, list[float]] = defaultdict(list)
    for _tick, ctx, depth_cents in shocks:
        plan = plan_ladder(ctx, depths, cfg)
        if not bucket_passes_backtest_filter(plan.bucket_key, cfg):
            continue
        depths[plan.bucket_key].append(depth_cents)
    return dict(depths)


def replay_paper(
    by_slug: dict[str, list[ParsedTick]],
    historical_depths: dict[str, list[float]],
    cfg: MatchShockConfig,
) -> dict[str, float]:
    """Replay shocks with frozen distribution file; return aggregate stats."""
    from world_cup_bot.match_shock import (
        bucket_passes_backtest_filter,
        plan_ladder,
        simulate_paper_fill,
        simulate_recovery_pnl,
    )

    wins = 0
    losses = 0
    total_pnl = 0.0

    for _slug, ticks in by_slug.items():
        shocks = scan_shocks(ticks, cfg)
        for tick, ctx, _depth_cents in shocks:
            plan = plan_ladder(ctx, historical_depths, cfg)
            if not bucket_passes_backtest_filter(plan.bucket_key, cfg):
                continue
            post_low = min(t.price for t in ticks if t.ts_ms >= tick.ts_ms)
            fill = simulate_paper_fill(plan, post_low)
            if fill is None:
                continue
            exit_price = min(plan.recovery_target_price, ctx.pre_price)
            pnl = simulate_recovery_pnl(fill, exit_price)
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            else:
                losses += 1

    n = wins + losses
    return {
        "trades": float(n),
        "wins": float(wins),
        "losses": float(losses),
        "win_rate": (wins / n) if n else 0.0,
        "total_pnl_usd": total_pnl,
        "window_ms": float(cfg.detection.window_ms),
    }
