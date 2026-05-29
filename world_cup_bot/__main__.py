"""CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from world_cup_bot import (
    advisor,
    calendar_guard,
    conviction,
    fill_handler,
    ledger,
    quoter,
    scanner,
    ws_user,
)
from world_cup_bot.clob_auth import MissingClobAuthError, load_clob_auth
from world_cup_bot.config import Settings
from world_cup_bot.logic_version import PnlScope, load_strategy_version
from world_cup_bot.operating_config import load_operating_config


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


def _cmd_scan(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    markets = _load_markets(settings)
    if args.eligible_only:
        markets = scanner.filter_lp_eligible(markets)

    if not markets:
        print("No advance markets found.")
        return 1

    cfg = None
    if args.conviction:
        cfg = conviction.load_conviction_config(Path(settings.conviction_config))

    if cfg:
        print(f"{'TEAM':24} {'MID':>6} {'MODE':>16} {'QUOTE':>5} {'LP':>3}  REASON")
        for m in markets:
            mid = f"{m.mid:.3f}" if m.mid is not None else "  —  "
            ev = conviction.evaluate_market(m, cfg)
            print(
                f"{m.team:24} {mid:>6} {ev.mode.value:>16} "
                f"{'Y' if ev.quote else 'N':>5} {'Y' if m.lp_eligible else 'N':>3}  {ev.reason}"
            )
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


def _cmd_plan(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    print(version_spec.version_banner())

    cfg = conviction.load_conviction_config(Path(settings.conviction_config))
    markets = _load_markets(settings)
    results = conviction.filter_conviction_markets(markets, cfg, quote_only=not args.all)

    if not results:
        print("No conviction targets (try --all to see skips).")
        return 1

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
        print("No targets after advisor gate.")
        return 1

    intents: list[quoter.QuoteIntent] = []
    for result in results:
        if result.quote:
            mult = multipliers.get(result.market.team, 1.0)
            intents.extend(quoter.build_quotes(result, cfg, settings, notional_multiplier=mult))

    quoter.submit_quotes(intents, settings)

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


def _cmd_watch(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    operating = load_operating_config(Path(settings.operating_config))
    print(version_spec.version_banner())

    try:
        auth = load_clob_auth()
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
        operating=operating,
        version_spec=version_spec,
        ledger_path=settings.ledger_path,
        dry_run=settings.dry_run,
        record=args.record,
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


def main(argv: list[str] | None = None) -> None:
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
    sc.set_defaults(eligible_only=True, func=_cmd_scan)

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
    pl.set_defaults(func=_cmd_plan)

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

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(0)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
