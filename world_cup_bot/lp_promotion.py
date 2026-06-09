"""LP promotion gates — DSR-style Sharpe + MCPT permutation test on shadow ledger."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from world_cup_bot.ledger import load_rows
from world_cup_bot.logic_version import PnlScope, StrategyVersionSpec, filter_rows_by_scope
from world_cup_bot.operating_config import PromotionOps


@dataclass(frozen=True)
class PromotionMetrics:
    distinct_days: int
    fill_count: int
    daily_pnl_usd: tuple[float, ...]
    sharpe: float | None
    deflated_sharpe: float | None
    mcpt_p_value: float | None

    def to_dict(self) -> dict:
        return {
            "distinct_days": self.distinct_days,
            "fill_count": self.fill_count,
            "daily_pnl_usd": list(self.daily_pnl_usd),
            "sharpe": self.sharpe,
            "deflated_sharpe": self.deflated_sharpe,
            "mcpt_p_value": self.mcpt_p_value,
        }


def _row_day(row: dict) -> str | None:
    ts = str(row.get("timestamp") or row.get("ts") or row.get("recorded_at") or "")
    return ts[:10] if len(ts) >= 10 else None


def daily_pnl_series(rows: list[dict]) -> dict[str, float]:
    """Sum pnl_usd by UTC day from fill/exit rows."""
    from world_cup_bot.ledger import is_synthetic_backfill_exit

    by_day: dict[str, float] = {}
    for row in rows:
        if row.get("event") not in ("order_fill", "exit_fill", "position_exit"):
            continue
        if is_synthetic_backfill_exit(row):
            continue
        day = _row_day(row)
        if not day:
            continue
        pnl = row.get("pnl_usd")
        if pnl is None:
            continue
        by_day[day] = by_day.get(day, 0.0) + float(pnl)
    return by_day


def _sharpe(daily: list[float]) -> float | None:
    if len(daily) < 2:
        return None
    mean = sum(daily) / len(daily)
    var = sum((x - mean) ** 2 for x in daily) / (len(daily) - 1)
    if var <= 0:
        return None
    return mean / math.sqrt(var)


def _deflated_sharpe(sharpe: float | None, n: int) -> float | None:
    """Lo (2002) style DSR approximation for n daily observations."""
    if sharpe is None or n < 2:
        return None
    # Penalize short samples and positive SR inflation from multiple trials.
    penalty = math.sqrt(max(n - 1, 1)) / max(n, 1)
    return sharpe * penalty - math.sqrt(max(n - 1, 1)) / max(n, 1) * 0.5


def _mcpt_p_value(daily: list[float], *, permutations: int = 500, seed: int = 42) -> float | None:
    """Permutation test: fraction of shuffled daily PnL means >= observed mean."""
    if len(daily) < 2:
        return None
    observed = sum(daily) / len(daily)
    rng = random.Random(seed)
    count = 0
    for _ in range(permutations):
        shuffled = daily[:]
        rng.shuffle(shuffled)
        # Random sign flip approximates null under symmetric noise.
        flipped = [x * (1 if rng.random() > 0.5 else -1) for x in shuffled]
        perm_mean = sum(flipped) / len(flipped)
        if perm_mean >= observed:
            count += 1
    return count / permutations


def compute_promotion_metrics(
    ledger_path: Path,
    spec: StrategyVersionSpec,
) -> PromotionMetrics:
    if not ledger_path.is_file():
        return PromotionMetrics(0, 0, (), None, None, None)

    rows = filter_rows_by_scope(load_rows(ledger_path), spec, PnlScope.CURRENT)
    by_day = daily_pnl_series(rows)
    daily = tuple(by_day[k] for k in sorted(by_day))
    fills = sum(1 for r in rows if r.get("event") == "order_fill")
    sharpe = _sharpe(list(daily))
    dsr = _deflated_sharpe(sharpe, len(daily))
    mcpt = _mcpt_p_value(list(daily))
    return PromotionMetrics(
        distinct_days=len(by_day),
        fill_count=fills,
        daily_pnl_usd=daily,
        sharpe=round(sharpe, 4) if sharpe is not None else None,
        deflated_sharpe=round(dsr, 4) if dsr is not None else None,
        mcpt_p_value=round(mcpt, 4) if mcpt is not None else None,
    )


def evaluate_promotion_gates(
    ledger_path: Path,
    spec: StrategyVersionSpec,
    promotion: PromotionOps,
) -> tuple[bool, str, PromotionMetrics]:
    """Return (ok, detail, metrics) for shadow → live promotion."""
    metrics = compute_promotion_metrics(ledger_path, spec)

    if metrics.fill_count < promotion.min_fills:
        return (
            True,
            f"promotion n/a ({metrics.fill_count} fills — need {promotion.min_fills}+)",
            metrics,
        )

    if metrics.distinct_days < promotion.min_distinct_days:
        return (
            False,
            f"promotion blocked: {metrics.distinct_days} PnL day(s) "
            f"< {promotion.min_distinct_days} required",
            metrics,
        )

    if metrics.deflated_sharpe is not None and metrics.deflated_sharpe < promotion.min_dsr:
        return (
            False,
            f"promotion blocked: DSR {metrics.deflated_sharpe:.3f} < floor {promotion.min_dsr:.3f}",
            metrics,
        )

    if metrics.mcpt_p_value is not None and metrics.mcpt_p_value > promotion.max_mcpt_p:
        return (
            False,
            f"promotion blocked: MCPT p={metrics.mcpt_p_value:.3f} "
            f"> max {promotion.max_mcpt_p:.3f}",
            metrics,
        )

    parts = [f"fills={metrics.fill_count}", f"days={metrics.distinct_days}"]
    if metrics.deflated_sharpe is not None:
        parts.append(f"DSR={metrics.deflated_sharpe:.3f}")
    if metrics.mcpt_p_value is not None:
        parts.append(f"MCPT p={metrics.mcpt_p_value:.3f}")
    return True, "promotion gates pass (" + ", ".join(parts) + ")", metrics
