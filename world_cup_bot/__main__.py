"""CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from world_cup_bot import (
    advisor,
    alerts,
    calendar_guard,
    conviction,
    conviction_patch,
    conviction_staleness,
    cross_venue_alerts,
    cross_venue_scanner,
    event_log,
    fill_handler,
    fixture_watch,
    ledger,
    liquidity_scanner,
    operating_config,
    order_manager,
    preflight,
    quoter,
    research,
    rewards_sync,
    risk,
    scanner,
    shadow_checklist,
    ws_user,
)
from world_cup_bot.clob_auth import (
    MissingClobAuthError,
    load_clob_auth,
    load_maker_address,
    load_poly_address,
)
from world_cup_bot.config import Settings
from world_cup_bot.cross_venue_config import load_cross_venue_config
from world_cup_bot.logic_version import PnlScope, load_strategy_version
from world_cup_bot.operating_config import load_operating_config
from world_cup_bot.ui_server import DEFAULT_HOST, DEFAULT_PORT, run_ui_server


def _ledger_summary_dict(settings: Settings, version_spec) -> dict | None:
    path = Path(settings.ledger_path)
    rows = ledger.load_rows(path)
    if not rows:
        return None
    summary = ledger.summarize_pnl(rows, version_spec, PnlScope.CURRENT)
    return {
        "scope": summary.scope,
        "row_count": summary.row_count,
        "fills": summary.fills,
        "net_pnl_usd": summary.net_pnl_usd,
    }


def _build_advisor_context(settings: Settings, markets: list[scanner.AdvanceMarket]):
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    operating = operating_config.load_operating_config()
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
    advisor_settings = advisor.AdvisorSettings.from_env()
    return advisor.build_decision_context(
        markets=markets,
        conviction=cfg,
        version_spec=version_spec,
        dry_run=settings.dry_run,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
        cancel_window=cancel_rows,
        ledger_summary=_ledger_summary_dict(settings, version_spec),
        prompt_path=advisor_settings.prompt_path,
        liquidity_by_team=liq_by_team,
        liquidity_cfg=liq_cfg,
        liquidity_gate=True,
    )


def _cmd_calendar(args: argparse.Namespace) -> int:
    schedule = calendar_guard.build_team_schedule()
    now = datetime.now(UTC)

    if args.team:
        hours = calendar_guard.hours_until_kickoff(args.team, now=now, schedule=schedule)
        nxt = calendar_guard.next_kickoff_utc(args.team, now=now, schedule=schedule)
        if nxt is None:
            print(f"{args.team}: no upcoming kickoff found in fixture data")
            return 1
        cancel = calendar_guard.must_cancel_orders(
            args.team,
            min_hours_before_kickoff=args.min_hours,
            now=now,
            schedule=schedule,
        )
        print(f"team:          {args.team}")
        print(f"next_kickoff:  {nxt.isoformat()}")
        print(f"hours_until:   {hours:.2f}")
        print(f"must_cancel:   {cancel} (threshold {args.min_hours}h)")
        return 0

    if args.cancel_window:
        rows = calendar_guard.teams_in_cancel_window(
            min_hours_before_kickoff=args.min_hours,
            now=now,
            schedule=schedule,
        )
        if not rows:
            print(f"No teams within {args.min_hours}h cancel window.")
            return 0
        print(f"Teams within {args.min_hours}h of kickoff ({len(rows)}):")
        for team, hours in rows:
            print(f"  {team:28} {hours:6.2f}h")
        return 0

    print("Use --team NAME and/or --cancel-window")
    return 1


def _load_markets(settings: Settings) -> list[scanner.AdvanceMarket]:
    return scanner.discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )


def _liquidity_context(
    settings: Settings,
    markets: list[scanner.AdvanceMarket],
    *,
    teams: set[str] | None = None,
) -> tuple[operating_config.LiquidityOps, dict[str, liquidity_scanner.LiquidityReport]]:
    operating = operating_config.load_operating_config()
    scan_targets = markets
    if teams:
        scan_targets = [m for m in markets if m.team in teams]
    return liquidity_scanner.liquidity_map_for_markets(
        scan_targets,
        clob_url=settings.clob_url,
        operating=operating,
    )


def _liquidity_gate_enabled(*, explicit_flag: bool) -> bool:
    operating = operating_config.load_operating_config()
    return explicit_flag or operating.liquidity.auto_clear_human_review


def _print_liquidity_report(report: liquidity_scanner.LiquidityReport) -> None:
    m = report.market
    mid = f"{report.midpoint:.3f}"
    gamma_liq = f"{report.gamma_liquidity:.0f}" if report.gamma_liquidity is not None else "—"
    band = f"{report.min_band_depth_usd:.0f}" if report.min_band_depth_usd is not None else "—"
    status = "PASS" if report.passes else "FAIL"
    print(
        f"{m.team:24} {mid:>6} {gamma_liq:>8} {band:>8} {status:>4}  "
        f"{'; '.join(report.reasons[:2])}"
    )
    if report.yes:
        y = report.yes
        print(
            f"  YES bid/ask band ${y.bid.depth_in_band_usd:.0f}/${y.ask.depth_in_band_usd:.0f} "
            f"({y.bid.levels}/{y.ask.levels} lvls) "
            f"full ${y.bid.depth_usd:.0f}/${y.ask.depth_usd:.0f}"
        )
    if report.no:
        n = report.no
        print(
            f"  NO  bid/ask band ${n.bid.depth_in_band_usd:.0f}/${n.ask.depth_in_band_usd:.0f} "
            f"({n.bid.levels}/{n.ask.levels} lvls) "
            f"full ${n.bid.depth_usd:.0f}/${n.ask.depth_usd:.0f}"
        )


def _cmd_conviction_staleness(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    markets = _load_markets(settings)
    staleness_alerts = conviction_staleness.scan_mid_staleness(
        markets,
        ledger_path=Path(settings.ledger_path),
        threshold_pp=args.threshold_pp,
    )
    if args.json:
        print(json.dumps([a.to_dict() for a in staleness_alerts], indent=2))
        return 0 if not staleness_alerts else 2

    if not staleness_alerts:
        print(f"No mid moves ≥{args.threshold_pp:.0f}pp vs ledger quote_intent baseline.")
        return 0

    print(f"{'TEAM':24} {'PLACED':>7} {'LIVE':>7} {'Δpp':>6}  REASON")
    for alert in staleness_alerts:
        print(
            f"{alert.team:24} {alert.mid_at_place:7.3f} {alert.live_mid:7.3f} "
            f"{alert.delta_pp:6.1f}  {alert.reason}"
        )
    if args.notify:
        for alert in staleness_alerts:
            alerts.notify(
                "conviction_staleness",
                f"MID_STALE {alert.team} {alert.delta_pp:.1f}pp — {alert.reason}",
                extra=alert.to_dict(),
            )
    print(f"\n{len(staleness_alerts)} staleness alert(s) — re-run conviction DR for flagged teams")
    return 2


def _cmd_fixture_check(args: argparse.Namespace) -> int:
    try:
        result = fixture_watch.check_fixtures(
            local_path=Path(args.local) if args.local else None,
            upstream_url=args.upstream_url,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"fixture-check failed: {exc}")
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    elif not result.has_changes:
        print(
            f"Fixtures in sync ({result.local_match_count} matches, "
            f"sha256={result.local_sha256[:12]}…)"
        )
    else:
        print(
            f"Fixture drift detected — local {result.local_match_count} vs "
            f"upstream {result.upstream_match_count} matches"
        )
        if result.local_sha256 != result.upstream_sha256 and not result.changes:
            print("  (file hash differs but no per-match diff parsed)")
        for change in result.changes:
            print(
                f"  {change.change_type:12} {change.team1} vs {change.team2} "
                f"({change.group}): {change.detail}"
            )

    if result.has_changes and args.notify:
        summary = (
            f"{len(result.changes)} fixture change(s) — refresh data/worldcup2026-fixtures.json"
        )
        alerts.notify("fixture_drift", summary, extra=result.to_dict())

    if args.apply:
        if not result.has_changes:
            print("Nothing to apply.")
            return 0
        path = fixture_watch.apply_upstream_fixtures(
            local_path=Path(args.local) if args.local else None,
            upstream_url=args.upstream_url,
        )
        print(f"Applied upstream fixtures → {path}")
        return 0

    return 2 if result.has_changes else 0


def _cmd_conviction_patch(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"File not found: {path}")
        return 1
    text = path.read_text(encoding="utf-8")
    patches = conviction_patch.parse_dr_patches(text)
    if not patches:
        print("No conviction patches parsed — expected DR appendix JSON with team + lp_posture")
        return 1

    rendered = conviction_patch.render_staged_yaml(patches)
    if args.stage:
        out = conviction_patch.stage_patches(patches, out_dir=Path(args.out_dir))
        print(f"Staged {len(patches)} patch(es) → {out}")
        print(rendered)
        return 0

    print(rendered)
    print(f"\n{len(patches)} patch(es) — merge into config/conviction.yaml manually")
    return 0


def _cmd_liquidity_scan(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    markets = _load_markets(settings)
    if args.eligible_only:
        markets = scanner.filter_lp_eligible(markets)
    if not markets:
        print("No advance markets found.")
        return 1

    team_filter = {args.team} if args.team else None
    if args.human_review_only:
        cfg = conviction.load_conviction_config(Path(settings.conviction_config))
        markets = [m for m in markets if cfg.team_mode(m.team) == conviction.TeamMode.HUMAN_REVIEW]
        if not markets:
            print("No human_review markets in current scan set.")
            return 1

    liq_cfg, liq_by_team = _liquidity_context(settings, markets, teams=team_filter)
    reports = [liq_by_team[m.team] for m in markets if m.team in liq_by_team]

    if args.json:
        print(liquidity_scanner.reports_to_json(reports))
        return 0

    print(f"{'TEAM':24} {'MID':>6} {'GAMMA$':>8} {'MINBAND':>8} {'GATE':>4}  REASON")
    print(
        f"(band depth: bid min ${liq_cfg.min_depth_within_reward_spread_usd:.0f}, "
        f"ask min ${liq_cfg.min_ask_depth_within_reward_spread_usd:.0f} — config/operating.yaml)"
    )
    for report in reports:
        _print_liquidity_report(report)

    passed = sum(1 for r in reports if r.passes)
    print(f"\n{passed}/{len(reports)} pass liquidity gate (CLOB /book, live)")
    return 0 if passed == len(reports) else 2


def _cmd_scan(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    markets = _load_markets(settings)
    if args.eligible_only:
        markets = scanner.filter_lp_eligible(markets)

    if not markets:
        print("No advance markets found.")
        return 1

    cfg = None
    liq_cfg = None
    liq_by_team: dict[str, liquidity_scanner.LiquidityReport] = {}
    if args.conviction:
        cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    use_liq = args.liquidity or (args.conviction and _liquidity_gate_enabled(explicit_flag=False))
    if use_liq:
        liq_cfg, liq_by_team = _liquidity_context(
            settings, markets, teams={args.team} if getattr(args, "team", None) else None
        )

    if cfg:
        header = f"{'TEAM':24} {'MID':>6} {'MODE':>16} {'QUOTE':>5} {'LP':>3}"
        if use_liq:
            header += f" {'DEPTH':>5}"
        print(f"{header}  REASON")
        for m in markets:
            if getattr(args, "team", None) and m.team != args.team:
                continue
            mid = f"{m.mid:.3f}" if m.mid is not None else "  —  "
            ev = conviction.evaluate_market(
                m,
                cfg,
                liquidity=liq_by_team.get(m.team),
                liquidity_cfg=liq_cfg,
                liquidity_gate=use_liq,
            )
            depth_col = ""
            if use_liq:
                rep = liq_by_team.get(m.team)
                if rep:
                    depth_col = f" {'PASS' if rep.passes else 'FAIL':>5}"
                else:
                    depth_col = f" {'—':>5}"
            print(
                f"{m.team:24} {mid:>6} {ev.mode.value:>16} "
                f"{'Y' if ev.quote else 'N':>5} {'Y' if m.lp_eligible else 'N':>3}"
                f"{depth_col}  {ev.reason}"
            )
    elif use_liq and not cfg:
        print(f"{'TEAM':24} {'MID':>6} {'GAMMA$':>8} {'MINBAND':>8} {'GATE':>4}  REASON")
        for m in markets:
            if getattr(args, "team", None) and m.team != args.team:
                continue
            rep = liq_by_team.get(m.team)
            if rep:
                _print_liquidity_report(rep)
    else:
        print(f"{'TEAM':24} {'MID':>6} {'SPRD':>6} {'LIQ':>8} {'HRS':>6} {'BIL':>4} {'LP':>3}")
        for m in markets:
            mid = f"{m.mid:.3f}" if m.mid is not None else "  —  "
            spr = f"{m.spread:.3f}" if m.spread is not None else "  —  "
            liq = f"{m.liquidity:8.0f}" if m.liquidity is not None else "       —"
            hrs = f"{m.hours_to_kickoff:6.1f}" if m.hours_to_kickoff is not None else "     —"
            print(
                f"{m.team:24} {mid:>6} {spr:>6} {liq:>8} {hrs:>6} "
                f"{'Y' if m.bilateral_mode else 'N':>4} {'Y' if m.lp_eligible else 'N':>3}"
            )
    print(f"\n{len(markets)} markets (live Gamma)")
    return 0


def _plan_abort(settings: Settings, reason: str, detail: str, *, exit_code: int = 1) -> int:
    event_log.log_event(
        "plan_abort",
        abort_reason=reason,
        detail=detail,
        dry_run=settings.dry_run,
    )
    print(detail)
    return exit_code


def _cmd_plan(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    print(version_spec.version_banner())

    operating = load_operating_config(Path(settings.operating_config))
    risk_ok, risk_detail = risk.check_daily_adverse_budget(
        Path(settings.ledger_path),
        operating,
        version_spec,
    )
    if not risk_ok:
        return _plan_abort(settings, "daily_adverse_cap", risk_detail)

    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    markets = _load_markets(settings)

    liq_cfg = None
    liq_by_team: dict[str, liquidity_scanner.LiquidityReport] = {}
    use_liq = _liquidity_gate_enabled(explicit_flag=args.liquidity_gate)
    if use_liq:
        liq_cfg, liq_by_team = _liquidity_context(settings, markets)

    results = conviction.filter_conviction_markets(
        markets,
        cfg,
        quote_only=not args.all,
        liquidity_by_team=liq_by_team if use_liq else None,
        liquidity_cfg=liq_cfg,
        liquidity_gate=use_liq,
    )

    if not results:
        return _plan_abort(
            settings,
            "no_conviction_targets",
            "No conviction targets (try --all to see skips).",
        )

    gate = advisor.AdvisorGate.OFF
    multipliers: dict[str, float] = {}
    if args.advisor:
        gate = advisor.AdvisorGate(args.advisor_gate)
        advisor_settings = advisor.AdvisorSettings.from_env()
        if not advisor_settings.configured:
            print(
                "Advisor not configured (ADVISOR_BASE_URL unset) — continuing without LLM. "
                "See SETUP.md § Optional LLM advisor."
            )
        else:
            try:
                ctx = _build_advisor_context(settings, markets)
                llm = advisor.load_advisor(advisor_settings)
                verdicts = llm.review(ctx)
                applied = advisor.apply_advisor_gates(results, verdicts, gate=gate)
                results = applied.kept
                multipliers = applied.multipliers
                if applied.skipped:
                    print("Advisor hard-gate skips:")
                    for row, v in applied.skipped:
                        reasons = ", ".join(v.reasons[:2])
                        print(f"  {row.market.team:20} {v.verdict.value:14} — {reasons}")
                if gate == advisor.AdvisorGate.SOFT and verdicts:
                    print("Advisor soft-gate notes:")
                    for v in verdicts:
                        if v.verdict != advisor.AdvisorVerdict.QUOTE or v.notional_multiplier < 1.0:
                            note = ", ".join(v.reasons[:2])
                            print(
                                f"  {v.team:20} {v.verdict.value:14} "
                                f"mult={v.notional_multiplier:.2f} — {note}"
                            )
            except (advisor.AdvisorNotConfiguredError, RuntimeError) as exc:
                print(f"Advisor error: {exc}")
                if args.advisor_strict:
                    return 1

    if not results:
        return _plan_abort(settings, "advisor_gate_empty", "No targets after advisor gate.")

    # Calendar guard: cancel resting quotes for teams entering kickoff window
    cancel_result = order_manager.cancel_for_cancel_window(
        settings,
        markets,
        ledger_path=settings.ledger_path,
        version_spec=version_spec,
    )
    if cancel_result.order_ids:
        mode = "DRY" if cancel_result.dry_run else "LIVE"
        print(
            f"Calendar cancel ({mode}): {len(cancel_result.order_ids)} order(s) — "
            f"{cancel_result.reason}"
        )

    # Drop conviction rows inside cancel window (must_cancel)
    results = [r for r in results if r.quote and not r.market.must_cancel]
    if not results:
        return _plan_abort(
            settings,
            "cancel_window",
            "No targets outside cancel window.",
        )

    intents: list[quoter.QuoteIntent] = []
    for result in results:
        if result.quote:
            mult = multipliers.get(result.market.team, 1.0)
            intents.extend(quoter.build_quotes(result, cfg, settings, notional_multiplier=mult))

    if not intents:
        return _plan_abort(
            settings,
            "zero_quote_intents",
            "Conviction rows matched but 0 quote intents built.",
        )

    quoter.submit_quotes(
        intents,
        settings,
        markets=markets,
        ledger_path=settings.ledger_path if args.record else None,
        version_spec=version_spec if args.record else None,
    )

    if args.record:
        n = ledger.record_quote_intents(
            intents,
            version_spec,
            path=Path(settings.ledger_path),
            dry_run=settings.dry_run,
        )
        print(f"Recorded {n} rows → {settings.ledger_path}")

    print(f"{'TEAM':20} {'SIDE':>4} {'PRICE':>6} {'SHARES':>8} {'USD':>8}  REASON")
    for q in intents:
        print(
            f"{q.team:20} {q.side:>4} {q.price:>6.2f} {q.size_shares:>8.1f} "
            f"{q.notional_usd:>8.0f}  {q.reason}"
        )

    mode = "DRY_RUN" if settings.dry_run else "LIVE"
    print(f"\n{len(intents)} quote intents ({mode}) from {len(results)} conviction rows")
    event_log.log_event(
        "plan_complete",
        intents=len(intents),
        conviction_rows=len(results),
        dry_run=settings.dry_run,
        recorded=bool(args.record),
    )
    return 0


def _cmd_research_list(_args: argparse.Namespace) -> int:
    print(f"{'MODE':24} AGENT PROMPT")
    for row in research.list_research_modes():
        mark = "" if row["exists"] == "True" else " (missing)"
        print(f"{row['mode']:24} {row['prompt']}{mark}")
    print("\nAgent JSON:  world-cup-bot research run <mode> --json")
    print("Gemini DR:   world-cup-bot research gemini <mode> [--group B] [--team X]")
    print("See prompts/README.md and prompts/gemini-deep-research/README.md")
    return 0


def _cmd_research_gemini(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    try:
        mode = research.ResearchMode(args.mode)
    except ValueError:
        print(f"Unknown mode {args.mode!r}. Use: world-cup-bot research list")
        return 1
    try:
        prompt = research.build_gemini_deep_research_prompt(
            mode,
            settings,
            group=args.group,
            team=args.team,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc))
        return 1
    print(prompt)
    return 0


def _cmd_research_run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    try:
        mode = research.ResearchMode(args.mode)
    except ValueError:
        print(f"Unknown mode {args.mode!r}. Use: world-cup-bot research list")
        return 1
    try:
        bundle = research.build_research_bundle(
            mode,
            settings,
            group=args.group,
            team=args.team,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc))
        return 1

    if args.messages:
        print(json.dumps(research.bundle_to_chat_messages(bundle), indent=2))
        return 0
    if args.json:
        print(json.dumps(bundle.to_dict(), indent=2))
        return 0

    print(f"mode:          {bundle.mode}")
    print(f"logic_version: {bundle.logic_version}")
    print(f"prompt:        prompts/{bundle.prompt_file}")
    print(f"output_schema: {bundle.output_schema}")
    print("\nUse --json for full bundle or --messages for chat API payload.")
    print("Paste prompts/{bundle.prompt_file} as system message with focus JSON as user.")
    return 0


def _cmd_context(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    markets = _load_markets(settings)
    if args.eligible_only:
        markets = scanner.filter_lp_eligible(markets)
    if not markets:
        print("No advance markets found.")
        return 1

    ctx = _build_advisor_context(settings, markets)
    if args.json:
        print(json.dumps(ctx.to_dict(), indent=2))
        return 0

    print(f"generated_at: {ctx.generated_at}")
    print(f"logic_version: {ctx.logic_version}")
    print(f"teams: {len(ctx.conviction_rows)}")
    if ctx.cancel_window:
        print(f"cancel_window: {len(ctx.cancel_window)} teams")
    quoting = [r for r in ctx.conviction_rows if r.get("quote_gate")]
    print(f"quote_gate_pass: {len(quoting)}")
    print("\nUse --json to pipe into Claude / ChatGPT / Ollama / local agent.")
    print("Prompt template: prompts/advisor.md")
    return 0


def _cmd_pnl(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    print(version_spec.version_banner())

    scope = PnlScope(args.scope)
    rows = ledger.load_rows(Path(settings.ledger_path))
    if not rows:
        print(f"No ledger rows at {settings.ledger_path}")
        return 1

    summary = ledger.summarize_pnl(rows, version_spec, scope)
    print(f"scope:            {summary.scope}")
    print(f"rows:             {summary.row_count}")
    print(f"quote_intents:    {summary.quote_intents}")
    print(f"fills:            {summary.fills}")
    print(f"realized_pnl_usd: {summary.realized_pnl_usd:+.2f}")
    print(f"rewards_usd:      {summary.rewards_usd:+.2f}")
    print(f"fees_usd:         {summary.fees_usd:+.2f}")
    print(f"net_pnl_usd:      {summary.net_pnl_usd:+.2f}")
    if summary.legacy_excluded:
        print(f"legacy_excluded:  {summary.legacy_excluded} rows (scope=current)")

    if args.by_version:
        print("\nBy logic_version:")
        for block in ledger.summarize_by_version(rows):
            print(
                f"  {block['logic_version']:24} rows={block['row_count']:4} "
                f"fills={block['fills']:3} net={block['net_pnl_usd']:+.2f}"
            )
    return 0


def _cmd_rewards_sync(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    markets = _load_markets(settings)

    if args.date:
        dates = [args.date]
    else:
        today = datetime.now(UTC).date()
        dates = [(today - timedelta(days=offset)).isoformat() for offset in range(1, args.days + 1)]

    try:
        results = rewards_sync.sync_rewards_range(
            settings,
            markets,
            version_spec,
            dates=dates,
            record=args.record,
            ledger_path=settings.ledger_path,
        )
    except MissingClobAuthError as exc:
        print(f"Rewards sync requires L2 creds: {exc}")
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(f"Rewards sync failed: {exc}")
        return 1

    if args.json:
        payload = [
            {
                "date": r.date,
                "fetched": r.fetched,
                "wc_matched": r.wc_matched,
                "recorded": r.recorded,
                "skipped_existing": r.skipped_existing,
                "rows": [
                    {
                        "team": row.team,
                        "rewards_usd": row.rewards_usd,
                        "reward_key": row.reward_key,
                    }
                    for row in r.rows
                ],
            }
            for r in results
        ]
        print(json.dumps(payload, indent=2))
        return 0

    total_recorded = 0
    total_usd = 0.0
    for result in results:
        print(
            f"{result.date}: fetched={result.fetched} wc={result.wc_matched} "
            f"recorded={result.recorded} skipped={result.skipped_existing}"
        )
        for row in result.rows:
            print(f"  {row.team:20} ${row.rewards_usd:.4f}")
            total_usd += row.rewards_usd
        total_recorded += result.recorded

    if args.record:
        print(f"\nRecorded {total_recorded} reward row(s) → {settings.ledger_path}")
    else:
        print("\nDry preview — pass --record to append reward_accrual rows")
    print(f"WC rewards total (preview): ${total_usd:.2f}")
    return 0


def _cmd_fill(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    operating = load_operating_config(Path(settings.operating_config))
    print(version_spec.version_banner())

    markets = _load_markets(settings)
    market = next((m for m in markets if m.team.lower() == args.team.lower()), None)
    if market is None:
        print(f"No advance market found for team {args.team!r}")
        return 1

    filled_at = datetime.now(UTC)
    side = args.side.upper()
    token_id = market.yes_token_id if side == "YES" else market.no_token_id

    fill = fill_handler.FillEvent(
        order_id=args.order_id,
        team=market.team,
        side=side,
        token_id=token_id,
        fill_price=args.price,
        fill_shares=args.shares,
        filled_at=filled_at,
    )

    result = fill_handler.handle_fill(
        fill,
        market,
        operating,
        ahead_notional_usd=args.ahead_usd,
        dry_run=settings.dry_run,
    )

    if args.record:
        ledger.record_fill(
            path=Path(settings.ledger_path),
            spec=version_spec,
            team=fill.team,
            side=fill.side,
            order_id=fill.order_id,
            price=fill.fill_price,
            size_shares=fill.fill_shares,
        )
        if result.exit_intent:
            ledger.record_exit_intent(
                result.exit_intent,
                version_spec,
                path=Path(settings.ledger_path),
                fill_order_id=fill.order_id,
                dry_run=settings.dry_run,
            )

    print(f"fill:         {fill.order_id} {fill.side} @ {fill.fill_price:.2f} x {fill.fill_shares}")
    print(f"kill_switch:  {result.kill_switch}")
    print(f"pull_quotes:  {result.pull_quotes}")
    print(f"reason:       {result.reason}")

    markets = _load_markets(settings)
    order_manager.apply_fill_safety_actions(
        settings,
        markets,
        team=fill.team,
        kill_switch=result.kill_switch,
        pull_quotes=result.pull_quotes,
        dry_run=settings.dry_run,
        ledger_path=settings.ledger_path,
        version_spec=version_spec,
    )

    if result.exit_intent:
        ex = result.exit_intent
        fill_handler.submit_exit(ex, dry_run=settings.dry_run)
        print(
            f"exit_intent:  {ex.order_id} {ex.side} @ {ex.price:.2f} x {ex.size_shares:.1f} "
            f"due {ex.due_by.isoformat()}"
        )
    else:
        print("exit_intent:  (none — kill switch active)")

    return 0


def _print_fill_result(result: fill_handler.FillHandlerResult) -> None:
    fill = result.fill
    print(
        f"fill:         {fill.order_id} {fill.team} {fill.side} "
        f"@ {fill.fill_price:.2f} x {fill.fill_shares:.1f}"
    )
    print(f"kill_switch:  {result.kill_switch}")
    print(f"pull_quotes:  {result.pull_quotes}")
    print(f"reason:       {result.reason}")
    if result.exit_intent:
        ex = result.exit_intent
        print(
            f"exit_intent:  {ex.order_id} {ex.side} @ {ex.price:.2f} x {ex.size_shares:.1f} "
            f"due {ex.due_by.isoformat()}"
        )
    else:
        print("exit_intent:  (none — kill switch active)")


def _cmd_cancel(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    markets = _load_markets(settings)
    version_spec = load_strategy_version(Path(settings.logic_version_config))

    dry_run = settings.dry_run if args.live is False else False
    if args.live:
        dry_run = False

    ledger_kw = {
        "ledger_path": settings.ledger_path,
        "version_spec": version_spec,
    }

    if args.cancel_window:
        result = order_manager.cancel_for_cancel_window(
            settings,
            markets,
            min_hours=args.min_hours,
            dry_run=dry_run,
            **ledger_kw,
        )
    elif args.team:
        result = order_manager.cancel_for_teams(
            settings,
            markets,
            {args.team},
            reason=f"manual cancel — {args.team}",
            dry_run=dry_run,
            **ledger_kw,
        )
    elif args.all_wc:
        result = order_manager.cancel_all_wc_orders(
            settings,
            markets,
            dry_run=dry_run,
            **ledger_kw,
        )
    else:
        print("Specify --cancel-window, --team NAME, or --all-wc")
        return 1

    mode = "DRY_RUN" if result.dry_run else "LIVE"
    if not result.order_ids:
        print(f"No open WC orders to cancel ({mode}).")
        return 0
    print(f"Cancelled {len(result.order_ids)} order(s) ({mode}) — {result.reason}")
    for oid in result.order_ids:
        print(f"  {oid}")
    return 0


def _cmd_orders(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    markets = _load_markets(settings)
    try:
        open_orders = order_manager.fetch_wc_open_orders(settings, markets)
    except Exception as exc:
        print(f"Could not fetch open orders: {exc}")
        return 1

    if args.cancel_window:
        rows = calendar_guard.teams_in_cancel_window(
            min_hours_before_kickoff=settings.min_hours_before_kickoff,
        )
        in_window = {team for team, _ in rows}
        open_orders = [o for o in open_orders if o.team in in_window]

    print(order_manager.format_orders_table(open_orders))
    print(f"\n{len(open_orders)} open WC advance order(s)")
    return 0


def _cmd_shadow_status(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    payload = shadow_checklist.ready_payload(settings, test_auth=not args.skip_auth)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"DRY_RUN={payload['dry_run']}  progress={payload['shadow_progress']}")
        print(f"Ledger path: {payload.get('ledger_path') or settings.ledger_path}")
        for step in payload["shadow_steps"]:
            print(f"  [{step['status']:7}] phase {step['phase']} {step['title']}: {step['detail']}")
        ledger_stats = payload["ledger"]
        print(
            f"Ledger: {ledger_stats['quote_intents']} intents, "
            f"{ledger_stats['fills']} fills, {ledger_stats['distinct_days']} day(s)"
        )

    min_phase = args.min_phase
    for step in payload["shadow_steps"]:
        if step["phase"] > min_phase:
            continue
        if step["status"] in {"blocked", "pending"}:
            if args.json:
                pass
            else:
                print(f"\nGate FAIL: phase {step['phase']} step '{step['id']}' is {step['status']}")
            return 1
    if not args.json:
        print(f"\nGate PASS through phase {min_phase}")
    return 0


def _cmd_preflight(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    report = preflight.run_preflight(settings, test_auth=not args.skip_auth)
    for check in report.checks:
        icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}[check.status.value]
        print(f"[{icon:4}] {check.name:16} {check.detail}")
    if report.ok:
        print("\nPreflight passed.")
        return 0
    print("\nPreflight failed — fix FAIL items before live LP.")
    return 1


def _cmd_watch(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    operating = load_operating_config(Path(settings.operating_config))
    print(version_spec.version_banner())

    try:
        auth = load_clob_auth()
        poly_address = load_poly_address()
        maker_address = load_maker_address()
    except MissingClobAuthError as exc:
        print(str(exc))
        return 1

    markets = _load_markets(settings)
    if args.eligible_only:
        markets = scanner.filter_lp_eligible(markets)
    if not markets:
        print("No advance markets to watch.")
        return 1

    ctx = ws_user.FillWatchContext(
        markets_by_condition={m.condition_id: m for m in markets},
        markets=markets,
        operating=operating,
        version_spec=version_spec,
        ledger_path=settings.ledger_path,
        dry_run=settings.dry_run,
        record=args.record,
        settings=settings,
        clob_url=settings.clob_url,
        auth=auth,
        poly_address=poly_address,
        maker_address=maker_address,
        on_result=_print_fill_result if args.verbose else None,
    )

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    condition_ids = sorted({m.condition_id for m in markets})
    print(
        f"watch: {len(markets)} teams, {len(condition_ids)} condition ids, "
        f"record={'on' if args.record else 'off'}, dry_run={settings.dry_run}"
    )
    print("Ctrl+C to stop.")

    try:
        asyncio.run(
            ws_user.watch_fills(
                ws_url=settings.ws_user_url,
                auth=auth,
                markets=markets,
                ctx=ctx,
            )
        )
    except KeyboardInterrupt:
        print("\nwatch stopped.")
    except ImportError as exc:
        print(str(exc))
        return 1

    stats = ctx.stats
    print(
        f"stats: messages={stats.messages} trades={stats.trades_seen} "
        f"fills={stats.fills_processed} dedup_skips={stats.fills_skipped_dedup} "
        f"unknown_market={stats.fills_skipped_unknown_market}"
    )
    return 0


def _cmd_ui(args: argparse.Namespace) -> int:
    host = args.host or DEFAULT_HOST
    port = args.port or DEFAULT_PORT
    run_ui_server(host=host, port=port)
    return 0


def _print_cross_venue_scan(result: cross_venue_scanner.CrossVenueScanResult) -> None:
    if result.blockers:
        print("Config blockers:")
        for b in result.blockers:
            print(f"  - {b}")
        print()

    print(
        f"PM markets: {result.pm_market_count}  Kalshi WC: {result.kalshi_market_count}  "
        f"threshold: {result.alert_threshold_pp:.1f}pp"
    )

    slug_warn = result.slug_warnings
    if slug_warn:
        print(f"\nSlug changes ({len(slug_warn)}) — update config/cross_venue.yaml:")
        for row in slug_warn:
            print(f"  {row.team:20} {row.slug_change_detail}")

    alerts = result.alerts
    if alerts:
        print(f"\nALERTS ({len(alerts)}):")
        for row in alerts:
            print(
                f"  {row.team:20} {row.market_type:18} gap={row.gap_pp:.1f}pp  "
                f"PM={row.pm_mid:.3f}  KAL={row.kalshi_mid:.3f}  {row.kalshi_ticker}"
            )
    else:
        print("\nNo alerts at current threshold.")

    print(f"\n{'TEAM':20} {'TYPE':18} {'GAP':>6} {'PM':>6} {'KAL':>6} {'ALERT':>5}  NOTES")
    for row in result.rows:
        gap = f"{row.gap_pp:.1f}" if row.gap_pp is not None else "   —"
        pm = f"{row.pm_mid:.3f}" if row.pm_mid is not None else "   —"
        kal = f"{row.kalshi_mid:.3f}" if row.kalshi_mid is not None else "   —"
        flag = "YES" if row.alert else ("BLK" if row.blocked else "no")
        note = row.block_reason or row.notes or ""
        if len(note) > 40:
            note = note[:37] + "..."
        print(f"{row.team:20} {row.market_type:18} {gap:>6} {pm:>6} {kal:>6} {flag:>5}  {note}")


def _cmd_cross_venue_scan(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    cfg = load_cross_venue_config(Path(settings.cross_venue_config))

    def _once() -> cross_venue_scanner.CrossVenueScanResult:
        return cross_venue_scanner.run_scan(
            cfg,
            gamma_url=settings.gamma_url,
            kalshi_base_url=settings.kalshi_base_url,
            team_filter=args.team,
            include_discoveries=args.discover or args.discover_only,
        )

    if args.discover_only:
        result = _once()
        new = [d for d in result.discoveries if not d.in_config]
        if args.json:
            print(json.dumps([d.to_dict() for d in new], indent=2))
            return 0
        print(
            f"Discovered {len(new)} pair(s) not in config "
            f"({len(result.discoveries)} total matched):"
        )
        for d in new:
            gap = f"{d.gap_pp:.1f}pp" if d.gap_pp is not None else "—"
            blk = f" BLOCKED: {d.block_reason}" if d.blocked else ""
            print(
                f"  {d.team:20} {d.market_type:18} gap={gap}  "
                f"pm={d.pm_slug[:32]}  kal={d.kalshi_ticker}{blk}"
            )
        print("\nPaste new rows into config/cross_venue.yaml after rules-hash review.")
        return 0

    import time

    while True:
        result = _once()
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        elif not args.alert_only:
            _print_cross_venue_scan(result)
        else:
            for row in result.alerts:
                line = (
                    f"ALERT {row.team} {row.market_type} gap={row.gap_pp:.1f}pp "
                    f"PM={row.pm_mid:.3f} KAL={row.kalshi_mid:.3f}"
                )
                print(line)
            for row in result.slug_warnings:
                print(f"SLUG_CHANGE {row.team}: {row.slug_change_detail}")
            cross_venue_alerts.notify_scan_results(result)
            if args.discover:
                new = [d for d in result.discoveries if not d.in_config]
                if new:
                    print(f"DISCOVER {len(new)} new pair(s) — run --discover-only for YAML rows")

        if args.once or not args.loop:
            exit_code = 2 if (result.alerts or result.slug_warnings) else 0
            return exit_code

        time.sleep(cfg.poll_interval_sec)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        prog="world-cup-bot",
        description="World Cup 2026 advance-market LP bot (early build)",
    )
    sub = parser.add_subparsers(dest="command")

    cal = sub.add_parser("calendar", help="Match calendar guard (fixture kickoffs)")
    cal.add_argument("--team", help="Team name (e.g. Mexico, USA, Turkey)")
    cal.add_argument(
        "--cancel-window",
        action="store_true",
        help="List all teams inside the pre-kickoff cancel window",
    )
    cal.add_argument(
        "--min-hours",
        type=float,
        default=10.0,
        help="Cancel if next kickoff is sooner than this (default: 10)",
    )
    cal.set_defaults(func=_cmd_calendar)

    cn = sub.add_parser(
        "cancel",
        help="Cancel resting WC advance orders (calendar guard / manual)",
    )
    cn.add_argument(
        "--cancel-window",
        action="store_true",
        help="Cancel all open orders for teams inside pre-kickoff window",
    )
    cn.add_argument("--team", help="Cancel open orders for one team")
    cn.add_argument(
        "--all-wc",
        action="store_true",
        help="Cancel every open WC advance order",
    )
    cn.add_argument(
        "--min-hours",
        type=float,
        default=None,
        help="Cancel window threshold (default: MIN_HOURS_BEFORE_KICKOFF env)",
    )
    cn.add_argument(
        "--live",
        action="store_true",
        help="Force live cancel even when DRY_RUN=true",
    )
    cn.set_defaults(func=_cmd_cancel)

    od = sub.add_parser("orders", help="List open WC advance orders (L2 auth required)")
    od.add_argument(
        "--cancel-window",
        action="store_true",
        help="Show only orders for teams inside cancel window",
    )
    od.set_defaults(func=_cmd_orders)

    sc = sub.add_parser("scan", help="Discover advance markets via Gamma (live prices)")
    sc.add_argument(
        "--all",
        dest="eligible_only",
        action="store_false",
        help="Include markets outside LP eligibility filter",
    )
    sc.add_argument(
        "--conviction",
        action="store_true",
        help="Show conviction tier + quote gate per team",
    )
    sc.add_argument(
        "--liquidity",
        action="store_true",
        help="Fetch CLOB /book depth; with --conviction, apply liquidity gate to human_review",
    )
    sc.add_argument("--team", help="Filter to one team (with --liquidity)")
    sc.set_defaults(eligible_only=True, func=_cmd_scan, liquidity=False)

    cs = sub.add_parser(
        "conviction-staleness",
        help="Alert when live mid moved vs last ledger quote_intent (DR trigger)",
    )
    cs.add_argument(
        "--threshold-pp",
        type=float,
        default=15.0,
        help="Min absolute mid move in percentage points (default: 15)",
    )
    cs.add_argument("--json", action="store_true", help="Machine-readable output")
    cs.add_argument(
        "--notify",
        action="store_true",
        help="POST alerts to WC_ALERT_WEBHOOK_URL when drift detected",
    )
    cs.set_defaults(func=_cmd_conviction_staleness, notify=False)

    fc = sub.add_parser(
        "fixture-check",
        help="Diff vendored fixtures vs openfootball upstream (alert-only)",
    )
    fc.add_argument(
        "--local",
        help="Local fixtures path (default: data/worldcup2026-fixtures.json)",
    )
    fc.add_argument(
        "--upstream-url",
        default=fixture_watch.DEFAULT_UPSTREAM_URL,
        help="openfootball upstream JSON URL",
    )
    fc.add_argument("--json", action="store_true", help="Machine-readable output")
    fc.add_argument(
        "--notify",
        action="store_true",
        help="POST to WC_ALERT_WEBHOOK_URL when drift detected",
    )
    fc.add_argument(
        "--apply",
        action="store_true",
        help="Replace local fixtures with upstream (operator refresh)",
    )
    fc.set_defaults(func=_cmd_fixture_check, notify=False)

    cp = sub.add_parser(
        "conviction-patch",
        help="Parse Gemini DR JSON → staged conviction.yaml snippets (manual merge)",
    )
    cp.add_argument("file", help="DR output file (markdown with JSON appendix)")
    cp.add_argument(
        "--stage",
        action="store_true",
        help="Write data/local/staged/conviction-patch-*.yaml",
    )
    cp.add_argument(
        "--out-dir",
        default="data/local/staged",
        help="Staging directory for --stage",
    )
    cp.set_defaults(func=_cmd_conviction_patch)

    lq = sub.add_parser(
        "liquidity-scan",
        help="CLOB order-book depth vs operating.yaml liquidity gates (public /book)",
    )
    lq.add_argument("--team", help="Single team only")
    lq.add_argument(
        "--human-review-only",
        action="store_true",
        help="Only teams with per_team mode=human_review (e.g. Morocco)",
    )
    lq.add_argument(
        "--all",
        dest="eligible_only",
        action="store_false",
        help="Include markets outside LP eligibility filter",
    )
    lq.add_argument("--json", action="store_true", help="Machine-readable report")
    lq.set_defaults(eligible_only=True, func=_cmd_liquidity_scan)

    pl = sub.add_parser(
        "plan",
        help="Conviction filter + dry-run quote intents (Gamma mids, no hardcoded prices)",
    )
    pl.add_argument(
        "--all",
        action="store_true",
        help="Include conviction rows that fail quote gate (no intents built)",
    )
    pl.add_argument(
        "--record",
        action="store_true",
        help="Append quote intents to JSONL ledger (data/local/ledger.jsonl)",
    )
    pl.add_argument(
        "--advisor",
        action="store_true",
        help="Optional LLM review (requires ADVISOR_BASE_URL — see SETUP.md)",
    )
    pl.add_argument(
        "--advisor-gate",
        choices=[g.value for g in advisor.AdvisorGate if g != advisor.AdvisorGate.OFF],
        default=advisor.AdvisorGate.SOFT.value,
        help="soft=log verdicts; hard=skip on skip/human_review (default: soft)",
    )
    pl.add_argument(
        "--advisor-strict",
        action="store_true",
        help="Exit non-zero if advisor is enabled but API call fails",
    )
    pl.add_argument(
        "--liquidity-gate",
        action="store_true",
        help="Fetch CLOB /book; auto-clear human_review when depth passes (see operating.yaml)",
    )
    pl.set_defaults(func=_cmd_plan, liquidity_gate=False)

    cx = sub.add_parser(
        "context",
        help="Export decision context JSON for external LLM / agent (no API call)",
    )
    cx.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON to stdout (pipe to any agent)",
    )
    cx.add_argument(
        "--all",
        dest="eligible_only",
        action="store_false",
        help="Include markets outside LP eligibility filter",
    )
    cx.set_defaults(eligible_only=True, func=_cmd_context)

    rs = sub.add_parser(
        "research",
        help="Deep research modes — targeted prompts + focused context (no API call)",
    )
    rs_sub = rs.add_subparsers(dest="research_command")

    rs_list = rs_sub.add_parser("list", help="List deep research modes")
    rs_list.set_defaults(func=_cmd_research_list)

    rs_run = rs_sub.add_parser("run", help="Build research bundle for an external agent")
    rs_run.add_argument(
        "mode",
        choices=[m.value for m in research.ResearchMode],
        help="Research mode (see prompts/README.md)",
    )
    rs_run.add_argument("--group", help="Group letter A–L (group-conviction mode)")
    rs_run.add_argument("--team", help="Team name (team-lp-risk mode)")
    rs_run.add_argument("--json", action="store_true", help="Print full JSON bundle")
    rs_run.add_argument(
        "--messages",
        action="store_true",
        help="Print OpenAI-style system+user messages JSON",
    )
    rs_run.set_defaults(func=_cmd_research_run)

    rs_gemini = rs_sub.add_parser(
        "gemini",
        help="Print copy-paste prompt for Gemini Deep Research (gemini.google.com)",
    )
    rs_gemini.add_argument(
        "mode",
        choices=[m.value for m in research.ResearchMode],
        help="Research mode (see prompts/gemini-deep-research/)",
    )
    rs_gemini.add_argument("--group", help="Group letter A–L (group-conviction mode)")
    rs_gemini.add_argument("--team", help="Team name (team-lp-risk mode)")
    rs_gemini.set_defaults(func=_cmd_research_gemini)

    pn = sub.add_parser(
        "pnl",
        help="P&L summary from ledger (default scope=current, K75 version filter)",
    )
    pn.add_argument(
        "--scope",
        choices=[s.value for s in PnlScope],
        default=PnlScope.CURRENT.value,
        help="current=active logic_version only; legacy=all old versions; all=unfiltered",
    )
    pn.add_argument(
        "--by-version",
        action="store_true",
        help="Print breakdown grouped by logic_version",
    )
    pn.set_defaults(func=_cmd_pnl)

    rw = sub.add_parser("rewards", help="Polymarket liquidity rewards (CLOB /rewards/user)")
    rw_sub = rw.add_subparsers(dest="rewards_cmd", required=True)
    rw_sync = rw_sub.add_parser("sync", help="Sync WC advance-market rewards into ledger")
    rw_sync.add_argument("--date", help="Single day YYYY-MM-DD (default: last N days)")
    rw_sync.add_argument(
        "--days",
        type=int,
        default=1,
        help="Backfill days ending today UTC when --date omitted (default: 1 = yesterday)",
    )
    rw_sync.add_argument("--record", action="store_true", help="Append reward_accrual rows")
    rw_sync.add_argument("--json", action="store_true", help="Machine-readable output")
    rw_sync.set_defaults(func=_cmd_rewards_sync)

    fl = sub.add_parser("fill", help="Handle a venue-confirmed fill → exit intent (Module 4)")
    fl.add_argument("--team", required=True, help="Team name (must match Gamma market)")
    fl.add_argument("--side", required=True, choices=["YES", "NO", "yes", "no"])
    fl.add_argument("--order-id", required=True, help="Venue fill order id (for dedup)")
    fl.add_argument("--price", type=float, required=True, help="Fill price")
    fl.add_argument("--shares", type=float, required=True, help="Fill size in shares")
    fl.add_argument(
        "--ahead-usd",
        type=float,
        default=0.0,
        help="Notional filled ahead of you in queue (queue depletion trigger)",
    )
    fl.add_argument("--record", action="store_true", help="Append fill + exit rows to ledger")
    fl.set_defaults(func=_cmd_fill)

    wch = sub.add_parser(
        "watch",
        help="Live user-channel WebSocket → fill handler (requires L2 API creds)",
    )
    wch.add_argument(
        "--all",
        dest="eligible_only",
        action="store_false",
        help="Subscribe to all discovered advance markets (not LP-filtered)",
    )
    wch.add_argument(
        "--record",
        action="store_true",
        help="Append venue-confirmed fills + exit intents to ledger",
    )
    wch.add_argument(
        "--verbose",
        action="store_true",
        help="Print each fill handler result to stdout",
    )
    wch.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    wch.set_defaults(eligible_only=True, func=_cmd_watch)

    pf = sub.add_parser(
        "preflight",
        help="Geoblock + Gamma + CLOB auth checks before live LP",
    )
    pf.add_argument(
        "--skip-auth",
        action="store_true",
        help="Skip L2 GET /data/orders auth probe",
    )
    pf.set_defaults(func=_cmd_preflight)

    ss = sub.add_parser(
        "shadow-status",
        help="SHADOW.md gate check — exit 1 if phase steps pending/blocked",
    )
    ss.add_argument(
        "--min-phase",
        type=int,
        default=1,
        help="Require steps through this phase to be done/warn (default: 1)",
    )
    ss.add_argument("--json", action="store_true", help="Print full ready payload JSON")
    ss.add_argument(
        "--skip-auth",
        action="store_true",
        help="Skip L2 auth probe when evaluating checklist",
    )
    ss.set_defaults(func=_cmd_shadow_status)

    ui = sub.add_parser(
        "ui",
        help="Optional read-only localhost dashboard (stdlib, no extra deps)",
    )
    ui.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Bind address (default: 127.0.0.1 — localhost only)",
    )
    ui.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Port (default: 8765)",
    )
    ui.set_defaults(func=_cmd_ui)

    cv = sub.add_parser(
        "cross-venue-scan",
        help="Module 6 — PM vs Kalshi gap alerts (read-only, no auto-trade)",
    )
    cv.add_argument("--team", help="Filter to one team (e.g. USA, Switzerland)")
    cv.add_argument("--json", action="store_true", help="Print full scan result as JSON")
    cv.add_argument(
        "--alert-only",
        action="store_true",
        help="Print only threshold alerts (+ slug warnings)",
    )
    cv.add_argument(
        "--once",
        action="store_true",
        help="Single poll (default; use --loop for continuous)",
    )
    cv.add_argument(
        "--loop",
        action="store_true",
        help="Poll continuously (interval from cross_venue.yaml poll_interval_sec)",
    )
    cv.add_argument(
        "--discover",
        action="store_true",
        help="Also report auto-discovered pairs not yet in config",
    )
    cv.add_argument(
        "--discover-only",
        action="store_true",
        help="List discovered PM↔Kalshi pairs for config/cross_venue.yaml (no config scan)",
    )
    cv.set_defaults(func=_cmd_cross_venue_scan, once=True, loop=False)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(0)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
