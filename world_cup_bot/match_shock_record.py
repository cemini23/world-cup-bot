"""Live match-shock tape recorder — market-channel WS → JSONL (Module 8)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from world_cup_bot.match_market_discovery import MatchMarket
from world_cup_bot.ws_market import MarketTapeContext, MarketWatchStats, watch_market_tape

logger = logging.getLogger(__name__)


@dataclass
class RecordSession:
    out_path: Path
    markets: list[MatchMarket]
    record: bool = True
    _handle: TextIO | None = field(default=None, repr=False)
    stats: MarketWatchStats = field(default_factory=MarketWatchStats)

    @property
    def asset_to_slug(self) -> dict[str, str]:
        return {m.yes_token_id: m.slug for m in self.markets if m.yes_token_id}

    @property
    def asset_ids(self) -> list[str]:
        return sorted(self.asset_to_slug.keys())

    def open(self) -> None:
        if self.record:
            self.out_path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.out_path.open("a", encoding="utf-8")

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def write_ticks(self, ticks: list[dict[str, Any]]) -> None:
        if not self.record or self._handle is None:
            return
        for tick in ticks:
            self._handle.write(json.dumps(tick, separators=(",", ":")) + "\n")
        self._handle.flush()


def default_tape_path(base_dir: Path | None = None) -> Path:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    root = base_dir or Path("data/local/shock_tapes")
    return root / f"{day}.jsonl"


async def run_record_session(
    *,
    ws_url: str,
    session: RecordSession,
) -> None:
    session.open()
    ctx = MarketTapeContext(
        asset_to_slug=session.asset_to_slug,
        on_ticks=session.write_ticks,
        stats=session.stats,
    )
    try:
        await watch_market_tape(
            ws_url=ws_url,
            asset_ids=session.asset_ids,
            ctx=ctx,
        )
    finally:
        session.close()
        session.stats = ctx.stats
