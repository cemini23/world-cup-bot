"""Read-only JSON payloads for the optional localhost UI."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot import advisor, calendar_guard, conviction, quoter, scanner
from world_cup_bot.config import Settings
from world_cup_bot.ledger import load_rows, summarize_by_version, summarize_pnl
from world_cup_bot.logic_version import PnlScope, load_strategy_version
from world_cup_bot.paths import PROJECT_ROOT
from world_cup_bot.quoter import QuoteIntent


def conviction_summary_payload(settings: Settings) -> dict[str, Any]:
    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    markets = scanner.discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )
    by_mode: dict[str, int] = {}
    group_b: list[dict[str, Any]] = []
    group_b_teams = frozenset({"Canada", "Switzerland", "Bosnia & Herzegovina", "Qatar"})
    for market in markets:
        ev = conviction.evaluate_market(market, cfg)
        by_mode[ev.mode.value] = by_mode.get(ev.mode.value, 0) + 1
        if market.team in group_b_teams:
            group_b.append(
                {
                    "team": market.team,
                    "mid": market.mid,
                    "mode": ev.mode.value,
                    "quote": ev.quote,
                    "reason": ev.reason,
                }
            )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "config_version": 2,
        "yaml_path": settings.conviction_config,
        "market_count": len(markets),
        "by_mode": by_mode,
        "group_b": group_b,
        "yes_conviction_count": len(cfg.yes_conviction),
        "bilateral_count": len(cfg.bilateral_only),
        "fade_watch_count": len(cfg.fade_watch),
    }


def meta_payload(settings: Settings) -> dict[str, Any]:
    spec = load_strategy_version(Path(settings.logic_version_config))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_key": spec.strategy_key,
        "logic_version": spec.version_id,
        "dry_run": settings.dry_run,
        "gamma_url": settings.gamma_url,
        "advisor_configured": advisor.AdvisorSettings.from_env().configured,
        "project_root": str(PROJECT_ROOT),
    }


def markets_payload(
    settings: Settings,
    *,
    eligible_only: bool = True,
) -> dict[str, Any]:
    markets = scanner.discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )
    if eligible_only:
        markets = scanner.filter_lp_eligible(markets)
    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    rows = []
    for market in markets:
        ev = conviction.evaluate_market(market, cfg)
        rows.append(
            {
                "team": market.team,
                "mid": market.mid,
                "spread": market.spread,
                "liquidity": market.liquidity,
                "hours_to_kickoff": market.hours_to_kickoff,
                "lp_eligible": market.lp_eligible,
                "bilateral_mode": market.bilateral_mode,
                "must_cancel": market.must_cancel,
                "mode": ev.mode.value,
                "quote": ev.quote,
                "reason": ev.reason,
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "count": len(rows),
        "eligible_only": eligible_only,
        "markets": rows,
    }


def plan_payload(settings: Settings) -> dict[str, Any]:
    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    markets = scanner.discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )
    results = conviction.filter_conviction_markets(markets, cfg, quote_only=True)
    intents: list[QuoteIntent] = []
    for result in results:
        if result.quote:
            intents.extend(quoter.build_quotes(result, cfg, settings))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "conviction_rows": len(results),
        "intent_count": len(intents),
        "dry_run": settings.dry_run,
        "intents": [_intent_dict(i) for i in intents],
    }


def _intent_dict(intent: QuoteIntent) -> dict[str, Any]:
    row = asdict(intent)
    row["snapshot"] = asdict(intent.snapshot)
    return row


def calendar_payload(settings: Settings) -> dict[str, Any]:
    schedule = calendar_guard.build_team_schedule()
    now = datetime.now(UTC)
    cancel_rows = calendar_guard.teams_in_cancel_window(
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
        now=now,
        schedule=schedule,
    )
    return {
        "generated_at": now.isoformat(),
        "min_hours_before_kickoff": settings.min_hours_before_kickoff,
        "cancel_window_count": len(cancel_rows),
        "cancel_window": [
            {"team": team, "hours_to_kickoff": round(hours, 2)} for team, hours in cancel_rows
        ],
    }


def pnl_payload(settings: Settings) -> dict[str, Any]:
    spec = load_strategy_version(Path(settings.logic_version_config))
    path = Path(settings.ledger_path)
    rows = load_rows(path)
    if not rows:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "ledger_path": str(path),
            "empty": True,
        }
    summary = summarize_pnl(rows, spec, PnlScope.CURRENT)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "ledger_path": str(path),
        "empty": False,
        "summary": asdict(summary),
        "by_version": summarize_by_version(rows),
    }


def advisor_context_payload(settings: Settings) -> dict[str, Any]:
    markets = scanner.discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )
    markets = scanner.filter_lp_eligible(markets)
    spec = load_strategy_version(Path(settings.logic_version_config))
    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    schedule = calendar_guard.build_team_schedule()
    now = datetime.now(UTC)
    cancel_rows = calendar_guard.teams_in_cancel_window(
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
        now=now,
        schedule=schedule,
    )
    ledger_rows = load_rows(Path(settings.ledger_path))
    ledger_summary = None
    if ledger_rows:
        s = summarize_pnl(ledger_rows, spec, PnlScope.CURRENT)
        ledger_summary = {
            "scope": s.scope,
            "row_count": s.row_count,
            "fills": s.fills,
            "net_pnl_usd": s.net_pnl_usd,
        }
    advisor_settings = advisor.AdvisorSettings.from_env()
    ctx = advisor.build_decision_context(
        markets=markets,
        conviction=cfg,
        version_spec=spec,
        dry_run=settings.dry_run,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
        cancel_window=cancel_rows,
        ledger_summary=ledger_summary,
        prompt_path=advisor_settings.prompt_path,
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "advisor_configured": advisor_settings.configured,
        "context": ctx.to_dict(),
    }
