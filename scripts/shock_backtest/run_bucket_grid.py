#!/usr/bin/env python3
"""Run bucket grid A–D backtests (vary backtest filters per OSINT wiki matrix)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_cup_bot.match_shock_config import (  # noqa: E402
    BacktestFilterConfig,
    MatchShockConfig,
    load_match_shock_config,
)
from world_cup_bot.shock_tape import (  # noqa: E402
    build_distributions,
    group_by_slug,
    load_ticks,
    replay_paper,
    scan_shocks,
)


@dataclass(frozen=True)
class GridRun:
    run_id: str
    allowed_favoritism: frozenset[str]
    allowed_league_tiers: frozenset[str]
    notes: str


GRID_RUNS: tuple[GridRun, ...] = (
    GridRun("A", frozenset(), frozenset({"deep"}), "Baseline — all favoritism, deep league"),
    GridRun("B", frozenset({"moderate_fav"}), frozenset({"deep"}), "RoH claim"),
    GridRun(
        "C",
        frozenset({"moderate_fav", "slight_fav"}),
        frozenset({"deep"}),
        "Expanded favoritism",
    ),
    GridRun(
        "D",
        frozenset({"moderate_fav"}),
        frozenset({"deep", "unknown"}),
        "WC slugs often unknown league",
    ),
)


def config_for_run(base: MatchShockConfig, run: GridRun) -> MatchShockConfig:
    bt = BacktestFilterConfig(
        allowed_favoritism=run.allowed_favoritism,
        allowed_league_tiers=run.allowed_league_tiers,
        min_recovery_rate=base.backtest.min_recovery_rate,
    )
    return replace(base, backtest=bt)


def run_grid(
    trades_jsonl: Path,
    *,
    config_path: Path | None = None,
    out_dir: Path,
) -> dict:
    base_cfg = load_match_shock_config(config_path)
    ticks = load_ticks(trades_jsonl)
    by_slug = group_by_slug(ticks)
    all_shocks = []
    for slug_ticks in by_slug.values():
        all_shocks.extend(scan_shocks(slug_ticks, base_cfg))

    out_dir.mkdir(parents=True, exist_ok=True)
    reports: dict[str, dict] = {}
    lines: list[str] = [
        "# Match-shock bucket grid A–D",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Tape: `{trades_jsonl}`",
        "",
        "| Run | Favoritism | League | Shocks | Trades | Win rate | PnL USD | Gate |",
        "|-----|------------|--------|--------|--------|----------|---------|------|",
    ]

    for run in GRID_RUNS:
        cfg = config_for_run(base_cfg, run)
        depths = build_distributions(all_shocks, cfg)
        replay = replay_paper(by_slug, depths, cfg)
        gate_ok = replay["trades"] == 0 or replay["win_rate"] >= cfg.backtest.min_recovery_rate
        entry = {
            "run_id": run.run_id,
            "notes": run.notes,
            "allowed_favoritism": sorted(run.allowed_favoritism),
            "allowed_league_tiers": sorted(run.allowed_league_tiers),
            "shocks_detected": len(all_shocks),
            "buckets_with_data": len(depths),
            "bucket_sample_counts": {k: len(v) for k, v in sorted(depths.items())},
            "replay": replay,
            "gate_pass": gate_ok,
            "min_recovery_rate": cfg.backtest.min_recovery_rate,
        }
        reports[run.run_id] = entry
        fav = ",".join(sorted(run.allowed_favoritism)) or "all"
        league = ",".join(sorted(run.allowed_league_tiers)) or "all"
        wr = f"{replay['win_rate']:.1%}" if replay["trades"] else "—"
        pnl = f"{replay['total_pnl_usd']:.2f}" if replay["trades"] else "—"
        gate = "PASS" if gate_ok else "FAIL"
        lines.append(
            f"| {run.run_id} | {fav} | {league} | {len(all_shocks)} | "
            f"{int(replay['trades'])} | {wr} | {pnl} | {gate} |"
        )

    report_path = out_dir / "replay_report.json"
    report_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    md_path = out_dir / "replay_report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"out_dir": str(out_dir), "runs": reports}


def main() -> int:
    parser = argparse.ArgumentParser(description="Match-shock bucket grid A–D")
    parser.add_argument("trades_jsonl", type=Path)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/local/shock_backtest"),
    )
    args = parser.parse_args()
    if not args.trades_jsonl.is_file():
        print(f"Missing tape: {args.trades_jsonl}", file=sys.stderr)
        return 1
    result = run_grid(args.trades_jsonl, config_path=args.config, out_dir=args.out_dir)
    print(json.dumps({"grid": result["out_dir"], "run_ids": list(result["runs"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
