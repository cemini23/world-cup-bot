"""Read-only JSON payloads for the optional localhost UI."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot import advisor, calendar_guard, conviction, liquidity_scanner, quoter, scanner
from world_cup_bot.config import Settings, match_shock_enabled
from world_cup_bot.ledger import load_rows, summarize_by_version, summarize_pnl
from world_cup_bot.logic_version import PnlScope, load_strategy_version
from world_cup_bot.match_market_discovery import discover_match_markets
from world_cup_bot.match_shock import MATCH_SHOCK_SPEC
from world_cup_bot.match_shock_config import load_match_shock_config
from world_cup_bot.operating_config import load_operating_config
from world_cup_bot.paths import PROJECT_ROOT
from world_cup_bot.quoter import QuoteIntent


def _liquidity_context(settings: Settings, markets: list[scanner.AdvanceMarket]):
    operating = load_operating_config()
    return liquidity_scanner.liquidity_map_for_markets(
        markets,
        clob_url=settings.clob_url,
        operating=operating,
    )


def conviction_summary_payload(settings: Settings) -> dict[str, Any]:
    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    markets = scanner.discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )
    liq_cfg, liq_by_team = _liquidity_context(settings, markets)
    by_mode: dict[str, int] = {}
    group_b: list[dict[str, Any]] = []
    group_b_teams = frozenset({"Canada", "Switzerland", "Bosnia & Herzegovina", "Qatar"})
    for market in markets:
        ev = conviction.evaluate_market(
            market,
            cfg,
            liquidity=liq_by_team.get(market.team),
            liquidity_cfg=liq_cfg,
            liquidity_gate=True,
        )
        by_mode[ev.mode.value] = by_mode.get(ev.mode.value, 0) + 1
        if market.team in group_b_teams:
            group_b.append(
                {
                    "team": market.team,
                    "mid": market.mid,
                    "mode": ev.mode.value,
                    "quote": ev.quote,
                    "reason": ev.reason,
                    "clob_depth_pass": liq_by_team[market.team].passes
                    if market.team in liq_by_team
                    else None,
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
        "liquidity_gate": True,
    }


def meta_payload(settings: Settings) -> dict[str, Any]:
    spec = load_strategy_version(Path(settings.logic_version_config))
    shock_cfg = load_match_shock_config()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_key": spec.strategy_key,
        "logic_version": spec.version_id,
        "match_shock_version": MATCH_SHOCK_SPEC.version_id,
        "match_shock_enabled": shock_cfg.enabled and match_shock_enabled(),
        "match_shock_yaml_enabled": shock_cfg.enabled,
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
    liq_cfg, liq_by_team = _liquidity_context(settings, markets)
    rows = []
    for market in markets:
        liq = liq_by_team.get(market.team)
        ev = conviction.evaluate_market(
            market,
            cfg,
            liquidity=liq,
            liquidity_cfg=liq_cfg,
            liquidity_gate=True,
        )
        row: dict[str, Any] = {
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
        if liq:
            row["clob_depth"] = liquidity_scanner.report_to_dict(liq)
        rows.append(row)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "count": len(rows),
        "eligible_only": eligible_only,
        "liquidity_gate": True,
        "markets": rows,
    }


def plan_payload(settings: Settings) -> dict[str, Any]:
    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    markets = scanner.discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )
    liq_cfg, liq_by_team = _liquidity_context(settings, markets)
    results = conviction.filter_conviction_markets(
        markets,
        cfg,
        quote_only=True,
        liquidity_by_team=liq_by_team,
        liquidity_cfg=liq_cfg,
        liquidity_gate=True,
    )
    intents: list[QuoteIntent] = []
    for result in results:
        if result.quote:
            intents.extend(quoter.build_quotes(result, cfg, settings))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "conviction_rows": len(results),
        "intent_count": len(intents),
        "dry_run": settings.dry_run,
        "liquidity_gate": True,
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
    operating = load_operating_config()
    liq_cfg, liq_by_team = liquidity_scanner.liquidity_map_for_markets(
        markets,
        clob_url=settings.clob_url,
        operating=operating,
    )
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
        liquidity_by_team=liq_by_team,
        liquidity_cfg=liq_cfg,
        liquidity_gate=True,
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "advisor_configured": advisor_settings.configured,
        "context": ctx.to_dict(),
    }


def _tape_dir_stats(tape_dir: Path) -> dict[str, Any]:
    if not tape_dir.is_dir():
        return {"path": str(tape_dir), "files": 0, "lines": 0}
    files = sorted(tape_dir.glob("*.jsonl"))
    lines = 0
    for path in files:
        try:
            with path.open(encoding="utf-8") as handle:
                for _ in handle:
                    lines += 1
        except OSError:
            continue
    return {"path": str(tape_dir), "files": len(files), "lines": lines}


def match_shock_payload(settings: Settings, *, limit: int = 80) -> dict[str, Any]:
    shock_cfg = load_match_shock_config()
    markets = discover_match_markets(settings.gamma_url)
    open_count = sum(1 for m in markets if m.accepting_orders)
    wc_2026_count = sum(1 for m in markets if "wc-2026" in m.slug or "world-cup-2026" in m.slug)
    tape_dir = Path(settings.match_shock_tape_dir)
    rows = [
        {
            "slug": m.slug,
            "question": m.question[:120],
            "accepting_orders": m.accepting_orders,
            "condition_id": m.condition_id[:18] + "…",
        }
        for m in markets[:limit]
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "logic_version": MATCH_SHOCK_SPEC.version_id,
        "yaml_enabled": shock_cfg.enabled,
        "env_enabled": match_shock_enabled(),
        "active": shock_cfg.enabled and match_shock_enabled(),
        "market_count": len(markets),
        "open_count": open_count,
        "wc_2026_count": wc_2026_count,
        "display_limit": limit,
        "tape": _tape_dir_stats(tape_dir),
        "markets": rows,
        "cli": {
            "discover": "world-cup-bot match-shock-discover --out data/local/match_markets.json",
            "export": "world-cup-bot match-shock-export --discovery data/local/match_markets.json",
            "record": "WC_SHOCK_ENABLED=1 world-cup-bot match-shock-record",
        },
    }
