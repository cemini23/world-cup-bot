"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from world_cup_bot import calendar_guard, conviction, ledger, quoter, scanner
from world_cup_bot.config import Settings
from world_cup_bot.logic_version import PnlScope, load_strategy_version


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

    intents: list[quoter.QuoteIntent] = []
    for result in results:
        if result.quote:
            intents.extend(quoter.build_quotes(result, cfg, settings))

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
    pl.set_defaults(func=_cmd_plan)

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

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(0)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
