"""In-play match-shock paper scanner loop (Module 8)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot.config import Settings, match_shock_enabled
from world_cup_bot.match_market_discovery import MatchMarket, load_discovery_json
from world_cup_bot.match_shock import (
    ShockDetection,
    plan_ladder,
    simulate_paper_fill,
    simulate_recovery_pnl,
)
from world_cup_bot.match_shock_config import MatchShockConfig, load_match_shock_config
from world_cup_bot.match_shock_ledger import (
    default_ledger_path,
    record_ladder_planned,
    record_paper_fill,
    record_shock_detected,
)
from world_cup_bot.match_shock_post import check_live_post_gates, submit_ladder
from world_cup_bot.shock_tape import group_by_slug, load_ticks, scan_shocks
from world_cup_bot.trading_mode import MarketKind, ModeHandoffConfig, resolve_trading_mode

PLAN_STATUS_FILE = Path("data/local/match_shock_plan.status")


@dataclass
class PlanSessionStats:
    shocks: int = 0
    ladders: int = 0
    paper_fills: int = 0
    live_posts: int = 0
    slugs_scanned: int = 0
    last_run_at: str = ""
    errors: list[str] = field(default_factory=list)


def write_plan_status(path: Path, stats: PlanSessionStats) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if stats.errors and all(is_benign_plan_error(err) for err in stats.errors):
        status = "skipped"
    elif stats.errors:
        status = "error"
    else:
        status = "ok"
    payload = {
        "status": status,
        "last_run_at": stats.last_run_at or datetime.now(UTC).isoformat(),
        "shocks": stats.shocks,
        "ladders": stats.ladders,
        "paper_fills": stats.paper_fills,
        "live_posts": stats.live_posts,
        "slugs_scanned": stats.slugs_scanned,
        "errors": stats.errors,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _mode_cfg(settings: Settings, shock_cfg: MatchShockConfig) -> ModeHandoffConfig:
    return ModeHandoffConfig(
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
        max_match_hours=2.0,
        shock_enabled=shock_cfg.enabled and match_shock_enabled(),
    )


def filter_in_play_markets(
    markets: list[MatchMarket],
    *,
    hours_by_slug: dict[str, float] | None = None,
    cfg: ModeHandoffConfig,
) -> list[MatchMarket]:
    """Keep match markets in SHOCK mode (in-play window)."""
    out: list[MatchMarket] = []
    for m in markets:
        hours = (hours_by_slug or {}).get(m.slug)
        decision = resolve_trading_mode(
            market_kind=MarketKind.MATCH,
            hours_to_kickoff=hours,
            cfg=cfg,
        )
        if decision.shock_active:
            out.append(m)
    return out


def process_tape_once(
    tape_path: Path,
    markets: list[MatchMarket],
    shock_cfg: MatchShockConfig,
    *,
    settings: Settings,
    historical_depths: dict[str, list[float]] | None = None,
    ledger_path: Path | None = None,
    live: bool = False,
    token_by_slug: dict[str, str] | None = None,
) -> PlanSessionStats:
    stats = PlanSessionStats(last_run_at=datetime.now(UTC).isoformat())
    ticks = load_ticks(tape_path)
    if not ticks:
        stats.errors.append(f"no ticks in {tape_path}")
        return stats

    slug_set = {m.slug for m in markets} if markets else None
    if slug_set:
        ticks = [t for t in ticks if t.slug in slug_set]

    by_slug = group_by_slug(ticks)
    stats.slugs_scanned = len(by_slug)
    depths = dict(historical_depths or {})
    tokens = token_by_slug or {m.slug: m.yes_token_id for m in markets}

    for slug, slug_ticks in by_slug.items():
        shocks = scan_shocks(slug_ticks, shock_cfg)
        for tick, ctx, depth_cents in shocks:
            stats.shocks += 1
            detection = ShockDetection(
                shock=True,
                peak=ctx.pre_price,
                floor=ctx.pre_price - depth_cents / 100.0,
                depth=depth_cents / 100.0,
                pre_price=ctx.pre_price,
            )
            plan = plan_ladder(ctx, depths, shock_cfg)
            if ledger_path:
                record_shock_detected(
                    ledger_path,
                    slug=slug,
                    detection=detection,
                    bucket_key=plan.bucket_key,
                    depth_cents=depth_cents,
                )
            stats.ladders += 1
            if ledger_path:
                record_ladder_planned(ledger_path, slug=slug, plan=plan)

            post_low = min(t.price for t in slug_ticks if t.ts_ms >= tick.ts_ms)
            fill = simulate_paper_fill(plan, post_low)
            if fill and ledger_path:
                exit_price = min(plan.recovery_target_price, ctx.pre_price)
                pnl = simulate_recovery_pnl(fill, exit_price)
                record_paper_fill(ledger_path, slug=slug, plan=plan, fill=fill, pnl_usd=pnl)
                stats.paper_fills += 1

            if live and tokens.get(slug):
                gate = check_live_post_gates(settings, shock_cfg)
                if gate.allowed:
                    posts = submit_ladder(
                        plan,
                        token_id=tokens[slug],
                        slug=slug,
                        settings=settings,
                        cfg=shock_cfg,
                        ledger_path=ledger_path,
                        dry_run=False,
                    )
                    stats.live_posts += len(posts)

    return stats


def is_benign_plan_error(message: str) -> bool:
    """Paper-mode gaps that should not fail systemd when Module 8 data plane is idle."""
    return any(marker in message for marker in ("no tape file", "shock disabled"))


def plan_session_exit_code(stats: PlanSessionStats) -> int:
    if stats.errors and stats.shocks == 0:
        if all(is_benign_plan_error(err) for err in stats.errors):
            return 0
        return 1
    return 0


def run_plan_once(
    settings: Settings,
    *,
    discover_json: Path | None = None,
    tape_path: Path | None = None,
    distributions_path: Path | None = None,
    shock_config_path: Path | None = None,
    ledger_path: Path | None = None,
    live: bool = False,
    status_path: Path | None = None,
) -> PlanSessionStats:
    shock_cfg = load_match_shock_config(shock_config_path)
    if not shock_cfg.enabled and not match_shock_enabled():
        return PlanSessionStats(
            errors=["shock disabled — set enabled in yaml or WC_SHOCK_ENABLED=1"]
        )

    markets: list[MatchMarket] = []
    if discover_json and discover_json.is_file():
        markets = load_discovery_json(discover_json)

    mode_cfg = _mode_cfg(settings, shock_cfg)
    markets = filter_in_play_markets(markets, cfg=mode_cfg)

    ledger = ledger_path or default_ledger_path(shock_cfg, settings.match_shock_tape_dir)
    depths: dict[str, list[float]] = {}
    if distributions_path and distributions_path.is_file():
        depths = json.loads(distributions_path.read_text(encoding="utf-8"))

    tape = tape_path
    if tape is None:
        tape_dir = Path(settings.match_shock_tape_dir)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        candidate = tape_dir / f"{day}.jsonl"
        if candidate.is_file():
            tape = candidate

    if tape is None or not tape.is_file():
        stats = PlanSessionStats(
            slugs_scanned=len(markets),
            errors=["no tape file — run match-shock-record or pass --tape"],
        )
        write_plan_status(status_path or PLAN_STATUS_FILE, stats)
        return stats

    token_by_slug = {m.slug: m.yes_token_id for m in markets}
    stats = process_tape_once(
        tape,
        markets,
        shock_cfg,
        settings=settings,
        historical_depths=depths,
        ledger_path=Path(ledger) if ledger else None,
        live=live,
        token_by_slug=token_by_slug,
    )
    write_plan_status(status_path or PLAN_STATUS_FILE, stats)
    return stats


def run_plan_loop(
    settings: Settings,
    *,
    interval_sec: float = 900.0,
    max_iterations: int | None = None,
    **kwargs: Any,
) -> None:
    n = 0
    while True:
        run_plan_once(settings, **kwargs)
        n += 1
        if max_iterations is not None and n >= max_iterations:
            break
        time.sleep(interval_sec)
