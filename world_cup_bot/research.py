"""Deep research mode — bundle targeted prompts with focused bot context."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from world_cup_bot import (
    calendar_guard,
    conviction,
    conviction_staleness,
    cross_venue_scanner,
    liquidity_scanner,
    scanner,
)
from world_cup_bot.calendar_guard import load_fixtures
from world_cup_bot.config import Settings
from world_cup_bot.conviction import ConvictionConfig, TeamMode, load_conviction_config
from world_cup_bot.cross_venue_config import load_cross_venue_config
from world_cup_bot.ledger import load_rows, summarize_pnl
from world_cup_bot.logic_version import PnlScope, load_strategy_version
from world_cup_bot.operating_config import load_operating_config
from world_cup_bot.shadow_checklist import ready_payload

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
GEMINI_PROMPTS_DIR = PROMPTS_DIR / "gemini-deep-research"

# Teams where third-place tiebreak / GD math matters (K82 matrix seeds)
_THIRD_PLACE_CANDIDATES = frozenset(
    {
        "Scotland",
        "Iran",
        "Panama",
        "Japan",
        "Cape Verde",
        "Ivory Coast",
        "Ecuador",
        "Senegal",
        "Norway",
        "Algeria",
        "Austria",
        "Paraguay",
        "Australia",
    }
)


class ResearchMode(StrEnum):
    GROUP_CONVICTION = "group-conviction"
    CROSS_VENUE = "cross-venue"
    TEAM_LP_RISK = "team-lp-risk"
    THIRD_PLACE_GD = "third-place-gd"
    CONVICTION_STALENESS = "conviction-staleness"
    SHADOW_WEEKLY = "shadow-weekly"
    MODULE6_SCANNER = "module6-scanner"
    KNOCKOUT_MARKET_MAP = "knockout-market-map"
    INPLAY_PREGAME_RISKS = "inplay-pregame-risks"
    TOURNAMENT_PHASE_ROUTER = "tournament-phase-router"
    WEEKLY_OSINT_PIPELINE = "weekly-osint-pipeline"


MODE_PROMPT_FILES: dict[ResearchMode, str] = {
    ResearchMode.GROUP_CONVICTION: "deep-research-group-conviction.md",
    ResearchMode.CROSS_VENUE: "deep-research-cross-venue-map.md",
    ResearchMode.TEAM_LP_RISK: "deep-research-team-lp-risk.md",
    ResearchMode.THIRD_PLACE_GD: "deep-research-third-place-gd.md",
    ResearchMode.CONVICTION_STALENESS: "deep-research-conviction-staleness.md",
    ResearchMode.SHADOW_WEEKLY: "deep-research-shadow-weekly.md",
    ResearchMode.MODULE6_SCANNER: "deep-research-module6-scanner.md",
    ResearchMode.KNOCKOUT_MARKET_MAP: "deep-research-knockout-market-map.md",
    ResearchMode.INPLAY_PREGAME_RISKS: "deep-research-inplay-pregame-risks.md",
    ResearchMode.TOURNAMENT_PHASE_ROUTER: "deep-research-tournament-phase-router.md",
    ResearchMode.WEEKLY_OSINT_PIPELINE: "deep-research-weekly-osint-pipeline.md",
}

GEMINI_PROMPT_FILES: dict[ResearchMode, str] = {
    ResearchMode.GROUP_CONVICTION: "01-group-conviction.md",
    ResearchMode.CROSS_VENUE: "02-cross-venue-polymarket-kalshi.md",
    ResearchMode.TEAM_LP_RISK: "03-team-lp-risk.md",
    ResearchMode.THIRD_PLACE_GD: "04-third-place-gd-math.md",
    ResearchMode.CONVICTION_STALENESS: "05-conviction-staleness-audit.md",
    ResearchMode.SHADOW_WEEKLY: "06-shadow-weekly-review.md",
    ResearchMode.MODULE6_SCANNER: "07-module6-scanner-spec.md",
    ResearchMode.KNOCKOUT_MARKET_MAP: "08-knockout-market-map.md",
    ResearchMode.INPLAY_PREGAME_RISKS: "09-inplay-pregame-lp-risks.md",
    ResearchMode.TOURNAMENT_PHASE_ROUTER: "10-tournament-phase-router-spec.md",
    ResearchMode.WEEKLY_OSINT_PIPELINE: "11-weekly-osint-pipeline.md",
}


@dataclass(frozen=True)
class ResearchBundle:
    mode: str
    generated_at: str
    logic_version: str
    prompt_file: str
    instructions: str
    focus: dict[str, Any]
    output_schema: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def list_research_modes() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for mode in ResearchMode:
        path = PROMPTS_DIR / MODE_PROMPT_FILES[mode]
        rows.append(
            {
                "mode": mode.value,
                "prompt": MODE_PROMPT_FILES[mode],
                "exists": str(path.is_file()),
            }
        )
    return rows


def _load_prompt(mode: ResearchMode) -> tuple[str, str]:
    filename = MODE_PROMPT_FILES[mode]
    path = PROMPTS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt: {path}")
    return filename, path.read_text(encoding="utf-8")


def teams_in_group(group: str, *, fixtures_path: Path | None = None) -> list[str]:
    """Return unique team names for Group A–L from bundled fixtures."""
    letter = group.strip().upper().replace("GROUP ", "").replace("GROUP", "")
    if len(letter) != 1 or letter < "A" or letter > "L":
        raise ValueError(f"Invalid group {group!r} — use A–L")
    target = f"Group {letter}"
    data = load_fixtures(fixtures_path)
    teams: set[str] = set()
    for match in data.get("matches") or []:
        if match.get("group") != target:
            continue
        for key in ("team1", "team2"):
            name = match.get(key)
            if name and isinstance(name, str):
                teams.add(name.strip())
    return sorted(teams)


def _yaml_tier(cfg: ConvictionConfig, team: str) -> str:
    mode = cfg.team_mode(team)
    cap = cfg.max_notional(team)
    return f"{mode.value} (cap ${cap:.0f})"


def _market_focus_row(
    market: scanner.AdvanceMarket,
    cfg: ConvictionConfig,
) -> dict[str, Any]:
    ev = conviction.evaluate_market(market, cfg)
    return {
        "team": market.team,
        "mid": market.mid,
        "spread": market.spread,
        "liquidity": market.liquidity,
        "hours_to_kickoff": market.hours_to_kickoff,
        "bilateral_mode": market.bilateral_mode,
        "lp_eligible": market.lp_eligible,
        "yaml_tier": _yaml_tier(cfg, market.team),
        "quote_gate": ev.quote,
        "quote_reason": ev.reason,
        "condition_id": market.condition_id,
    }


def _markets_by_team(
    settings: Settings,
) -> tuple[list[scanner.AdvanceMarket], dict[str, scanner.AdvanceMarket]]:
    markets = scanner.discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )
    by_team = {m.team: m for m in markets}
    return markets, by_team


def build_research_bundle(
    mode: ResearchMode,
    settings: Settings,
    *,
    group: str | None = None,
    team: str | None = None,
) -> ResearchBundle:
    prompt_file, instructions = _load_prompt(mode)
    spec = load_strategy_version(Path(settings.logic_version_config))
    cfg = load_conviction_config(Path(settings.conviction_config))
    operating = load_operating_config(Path(settings.operating_config))
    markets, by_team = _markets_by_team(settings)
    schedule = calendar_guard.build_team_schedule()
    now = datetime.now(UTC)
    cancel_rows = calendar_guard.teams_in_cancel_window(
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
        now=now,
        schedule=schedule,
    )

    focus: dict[str, Any] = {
        "dry_run": settings.dry_run,
        "conviction_config": settings.conviction_config,
        "cancel_window": [{"team": t, "hours": round(h, 2)} for t, h in cancel_rows],
    }

    if mode == ResearchMode.GROUP_CONVICTION:
        if not group:
            raise ValueError("--group required for group-conviction (e.g. B)")
        group_teams = teams_in_group(group)
        focus["group"] = group.strip().upper()
        focus["fixture_teams"] = group_teams
        focus["teams"] = []
        for t in group_teams:
            m = by_team.get(t)
            if m:
                focus["teams"].append(_market_focus_row(m, cfg))
            else:
                focus["teams"].append(
                    {"team": t, "gamma_market": "not_found", "yaml_tier": _yaml_tier(cfg, t)}
                )

    elif mode == ResearchMode.CROSS_VENUE:
        fade = sorted(cfg.fade_watch)
        focus["fade_watch_teams"] = fade
        focus["markets"] = [_market_focus_row(by_team[t], cfg) for t in fade if t in by_team]
        cv_cfg = load_cross_venue_config()
        scan = cross_venue_scanner.run_scan(cv_cfg, gamma_url=settings.gamma_url)
        focus["live_cross_venue_alerts"] = [r.to_dict() for r in scan.alerts]
        focus["slug_warnings"] = [r.to_dict() for r in scan.slug_warnings]
        focus["known_research_flags"] = [
            {
                "team": row.team,
                "market_type": row.market_type,
                "gap_pp": row.gap_pp,
                "blocked": row.blocked,
                "block_reason": row.block_reason,
                "slug_changed": row.slug_changed,
                "alert": row.alert,
            }
            for row in scan.rows
            if row.alert or row.slug_changed or row.blocked
        ][:25]

    elif mode == ResearchMode.TEAM_LP_RISK:
        if not team:
            raise ValueError("--team required for team-lp-risk")
        m = by_team.get(team) or next((x for x in markets if x.team.lower() == team.lower()), None)
        if m is None:
            raise ValueError(f"No Gamma advance market for team {team!r}")
        focus["team"] = m.team
        focus["market"] = _market_focus_row(m, cfg)
        operating = load_operating_config()
        depth = liquidity_scanner.scan_market_liquidity(
            m,
            clob_url=settings.clob_url,
            cfg=operating.liquidity,
            bilateral=operating.bilateral,
        )
        focus["clob_depth"] = liquidity_scanner.report_to_dict(depth)
        liquidity = operating.liquidity
        focus["operating_thresholds"] = {
            "exit_within_seconds": operating.fill_handler.exit_within_seconds,
            "queue_depletion_usd": operating.fill_handler.queue_depletion_usd,
            "min_depth_within_reward_spread_usd": liquidity.min_depth_within_reward_spread_usd,
            "min_ask_depth_within_reward_spread_usd": (
                liquidity.min_ask_depth_within_reward_spread_usd
            ),
            "min_hours_before_kickoff": settings.min_hours_before_kickoff,
        }

    elif mode == ResearchMode.THIRD_PLACE_GD:
        candidates = sorted(_THIRD_PLACE_CANDIDATES)
        focus["third_place_candidates"] = candidates
        focus["teams"] = [_market_focus_row(by_team[t], cfg) for t in candidates if t in by_team]
        focus["tiebreak_order"] = [
            "points",
            "goal_difference",
            "goals_scored",
            "head_to_head",
            "fair_play",
            "lots",
        ]

    elif mode == ResearchMode.CONVICTION_STALENESS:
        rows = [conviction.evaluate_market(m, cfg) for m in markets]
        focus["all_teams"] = [
            {
                **_market_focus_row(r.market, cfg),
                "conviction_mode": r.mode.value,
            }
            for r in rows
            if r.mode != TeamMode.UNLISTED
        ]
        focus["staleness_alerts"] = [
            a.to_dict()
            for a in conviction_staleness.scan_mid_staleness(
                markets,
                ledger_path=Path(settings.ledger_path),
            )
        ]
        focus["yaml_summary"] = {
            "yes_conviction_count": len(cfg.yes_conviction),
            "bilateral_count": len(cfg.bilateral_only),
            "fade_watch_count": len(cfg.fade_watch),
        }

    elif mode == ResearchMode.SHADOW_WEEKLY:
        focus["ready"] = ready_payload(settings, test_auth=False)
        path = Path(settings.ledger_path)
        if path.is_file():
            rows = load_rows(path)
            summary = summarize_pnl(rows, spec, PnlScope.CURRENT)
            focus["pnl"] = asdict(summary)
        else:
            focus["pnl"] = None

    elif mode == ResearchMode.MODULE6_SCANNER:
        cv_cfg = load_cross_venue_config(Path(settings.cross_venue_config))
        focus["fade_watch_teams"] = sorted(cfg.fade_watch)
        focus["alert_threshold_pp"] = cv_cfg.alert_threshold_pp
        focus["poll_interval_sec"] = cv_cfg.poll_interval_sec
        focus["config_pairs"] = len(cv_cfg.pairs)
        focus["discovery_prefixes"] = list(cv_cfg.discovery.kalshi_ticker_prefixes)
        focus["pm_contract_pattern"] = (
            "Will {Team} advance to the knockout stages at the 2026 FIFA World Cup?"
        )
        focus["kalshi_pattern_hint"] = "KXWCGROUPWIN / KXWCGROUPQUAL / KXWCROUND tickers"
        focus["implementation_status"] = "built"
        focus["cli"] = "world-cup-bot cross-venue-scan [--discover-only] [--loop]"

    elif mode == ResearchMode.KNOCKOUT_MARKET_MAP:
        focus["active_phase"] = "group_advance"
        focus["market_phases_stub"] = "config/market_phases.yaml"
        focus["known_pm_events"] = [
            "world-cup-team-to-advance-to-knockout-stages",
            "world-cup-nation-to-reach-final",
            "2026-fifa-world-cup-winner",
        ]
        focus["scanner_regex_today"] = (
            "Will {Team} advance to the knockout stages at the 2026 FIFA World Cup?"
        )

    elif mode == ResearchMode.INPLAY_PREGAME_RISKS:
        focus["operating"] = {
            "cancel_hours": settings.min_hours_before_kickoff,
            "prefer_hours": operating.calendar.prefer_hours_before_kickoff,
            "exit_within_seconds": operating.fill_handler.exit_within_seconds,
        }
        focus["policy_v1"] = "no_in_play_quotes"

    elif mode == ResearchMode.TOURNAMENT_PHASE_ROUTER:
        focus["logic_version"] = spec.version_id
        focus["market_phases_stub"] = "config/market_phases.yaml"
        focus["modules_to_extend"] = ["scanner", "conviction", "calendar_guard", "ledger"]

    return ResearchBundle(
        mode=mode.value,
        generated_at=now.isoformat(),
        logic_version=spec.version_id,
        prompt_file=prompt_file,
        instructions=instructions,
        focus=focus,
        output_schema=_output_schema_hint(mode),
    )


def _output_schema_hint(mode: ResearchMode) -> str:
    hints = {
        ResearchMode.GROUP_CONVICTION: "GroupConvictionPatch JSON (see prompt)",
        ResearchMode.CROSS_VENUE: "CrossVenueReport JSON array",
        ResearchMode.TEAM_LP_RISK: "TeamLpRiskReport JSON object",
        ResearchMode.THIRD_PLACE_GD: "ThirdPlaceGdReport JSON object",
        ResearchMode.CONVICTION_STALENESS: "ConvictionStalenessPatch JSON",
        ResearchMode.SHADOW_WEEKLY: "ShadowWeeklyReview JSON object",
        ResearchMode.MODULE6_SCANNER: "Module6ScannerSpec JSON object",
        ResearchMode.KNOCKOUT_MARKET_MAP: "MarketPhases YAML appendix JSON",
        ResearchMode.INPLAY_PREGAME_RISKS: "InplayPregameRisk JSON object",
        ResearchMode.TOURNAMENT_PHASE_ROUTER: "TournamentPhaseRouterSpec JSON object",
        ResearchMode.WEEKLY_OSINT_PIPELINE: "WeeklyOsintPipeline JSON object",
    }
    return hints[mode]


def _load_gemini_template(mode: ResearchMode) -> str:
    filename = GEMINI_PROMPT_FILES[mode]
    path = GEMINI_PROMPTS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing Gemini prompt: {path}")
    return path.read_text(encoding="utf-8")


def build_gemini_deep_research_prompt(
    mode: ResearchMode,
    settings: Settings,
    *,
    group: str | None = None,
    team: str | None = None,
) -> str:
    """Single copy-paste block for gemini.google.com Deep Research."""
    bundle = build_research_bundle(mode, settings, group=group, team=team)
    template = _load_gemini_template(mode)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    context_json = json.dumps(bundle.focus, indent=2, default=str)

    group_letter = (group or bundle.focus.get("group") or "B").strip().upper()
    group_letter = group_letter.replace("GROUP ", "").replace("GROUP", "")
    fixture_teams = bundle.focus.get("fixture_teams")
    if not fixture_teams and group_letter:
        try:
            fixture_teams = teams_in_group(group_letter)
        except ValueError:
            fixture_teams = []
    fixture_str = ", ".join(fixture_teams) if fixture_teams else "(see attached context)"

    team_name = team or bundle.focus.get("team") or "TEAM"

    out = template.replace("{{DATE}}", today)
    out = out.replace("{{BOT_CONTEXT}}", context_json)
    out = out.replace("{{GROUP}}", group_letter)
    out = out.replace("{{FIXTURE_TEAMS}}", fixture_str)
    out = out.replace("{{TEAM}}", str(team_name))
    return out.strip()


def bundle_to_chat_messages(bundle: ResearchBundle) -> list[dict[str, str]]:
    """OpenAI-compatible message list for external agents."""
    user = (
        f"Deep research mode: {bundle.mode}\n"
        f"Logic version: {bundle.logic_version}\n"
        f"Return ONLY the JSON schema described in instructions.\n\n"
        f"## Focus context\n```json\n{json.dumps(bundle.focus, indent=2, default=str)}\n```"
    )
    return [
        {"role": "system", "content": bundle.instructions},
        {"role": "user", "content": user},
    ]
