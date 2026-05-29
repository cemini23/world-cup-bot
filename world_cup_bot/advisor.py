"""Optional LLM advisor — context export + advisory gates (never required for core LP)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from world_cup_bot.conviction import ConvictionConfig, ConvictionResult, evaluate_market
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.scanner import AdvanceMarket

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "advisor.md"


class AdvisorVerdict(StrEnum):
    QUOTE = "quote"
    SKIP = "skip"
    REDUCE = "reduce"
    HUMAN_REVIEW = "human_review"


class AdvisorGate(StrEnum):
    OFF = "off"
    SOFT = "soft"
    HARD = "hard"


@dataclass(frozen=True)
class AdvisorSettings:
    """Loaded from env only when operator opts in — no keys required by default."""

    base_url: str | None
    api_key: str | None
    model: str
    timeout_sec: float
    prompt_path: Path

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.base_url.strip())

    @classmethod
    def from_env(cls) -> AdvisorSettings:
        import os

        raw_url = os.environ.get("ADVISOR_BASE_URL", "").strip()
        return cls(
            base_url=raw_url or None,
            api_key=os.environ.get("ADVISOR_API_KEY", "").strip() or None,
            model=os.environ.get("ADVISOR_MODEL", "gpt-4o-mini").strip(),
            timeout_sec=float(os.environ.get("ADVISOR_TIMEOUT_SEC", "60")),
            prompt_path=Path(os.environ.get("ADVISOR_PROMPT", str(DEFAULT_PROMPT))),
        )


@dataclass(frozen=True)
class TeamAdvisorVerdict:
    team: str
    verdict: AdvisorVerdict
    confidence: float
    notional_multiplier: float
    reasons: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    signal_quality: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "notional_multiplier": self.notional_multiplier,
            "reasons": self.reasons,
            "risk_factors": self.risk_factors,
            "signal_quality": self.signal_quality,
        }


@dataclass(frozen=True)
class DecisionContext:
    generated_at: str
    logic_version: str
    strategy_key: str
    dry_run: bool
    min_hours_before_kickoff: float
    cancel_window: list[dict[str, Any]]
    conviction_rows: list[dict[str, Any]]
    ledger_summary: dict[str, Any] | None
    advisor_instructions: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _market_row(
    market: AdvanceMarket,
    result: ConvictionResult,
    cfg: ConvictionConfig,
) -> dict[str, Any]:
    return {
        "team": market.team,
        "condition_id": market.condition_id,
        "mid": market.mid,
        "spread": market.spread,
        "liquidity": market.liquidity,
        "hours_to_kickoff": market.hours_to_kickoff,
        "must_cancel": market.must_cancel,
        "bilateral_mode": market.bilateral_mode,
        "lp_eligible": market.lp_eligible,
        "rewards_min_shares": market.rewards_min_shares,
        "rewards_max_spread": market.rewards_max_spread,
        "conviction_mode": result.mode.value,
        "quote_gate": result.quote,
        "quote_reason": result.reason,
        "max_notional_usd": cfg.max_notional(market.team),
    }


def build_decision_context(
    *,
    markets: list[AdvanceMarket],
    conviction: ConvictionConfig,
    version_spec: StrategyVersionSpec,
    dry_run: bool,
    min_hours_before_kickoff: float,
    cancel_window: list[tuple[str, float]],
    ledger_summary: dict[str, Any] | None,
    prompt_path: Path | None = None,
) -> DecisionContext:
    prompt = prompt_path or DEFAULT_PROMPT
    instructions = ""
    if prompt.is_file():
        instructions = prompt.read_text(encoding="utf-8")

    rows = [evaluate_market(m, conviction) for m in markets]
    return DecisionContext(
        generated_at=datetime.now(UTC).isoformat(),
        logic_version=version_spec.version_id,
        strategy_key=version_spec.strategy_key,
        dry_run=dry_run,
        min_hours_before_kickoff=min_hours_before_kickoff,
        cancel_window=[
            {"team": team, "hours_to_kickoff": round(hours, 2)} for team, hours in cancel_window
        ],
        conviction_rows=[_market_row(r.market, r, conviction) for r in rows],
        ledger_summary=ledger_summary,
        advisor_instructions=instructions,
    )


def _clamp_multiplier(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_verdict_payload(raw: dict[str, Any]) -> TeamAdvisorVerdict | None:
    team = raw.get("team")
    verdict_str = raw.get("verdict")
    if not team or not verdict_str:
        return None
    try:
        verdict = AdvisorVerdict(str(verdict_str).lower())
    except ValueError:
        return None
    multiplier = _clamp_multiplier(float(raw.get("notional_multiplier", 1.0)))
    if verdict in {AdvisorVerdict.SKIP, AdvisorVerdict.HUMAN_REVIEW}:
        multiplier = 0.0
    elif verdict == AdvisorVerdict.REDUCE and multiplier >= 1.0:
        multiplier = 0.5
    return TeamAdvisorVerdict(
        team=str(team),
        verdict=verdict,
        confidence=_clamp_confidence(float(raw.get("confidence", 0.5))),
        notional_multiplier=multiplier,
        reasons=[str(x) for x in raw.get("reasons") or []][:5],
        risk_factors=[str(x) for x in raw.get("risk_factors") or []][:5],
        signal_quality=str(raw["signal_quality"]) if raw.get("signal_quality") else None,
    )


_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def parse_advisor_response(text: str) -> list[TeamAdvisorVerdict]:
    """Parse model output — JSON array or fenced block."""
    stripped = text.strip()
    candidates = [stripped]
    for match in _JSON_BLOCK.finditer(text):
        candidates.append(match.group(1).strip())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("verdicts") or data.get("teams") or []
        if not isinstance(items, list):
            continue
        verdicts: list[TeamAdvisorVerdict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parsed = parse_verdict_payload(item)
            if parsed:
                verdicts.append(parsed)
        if verdicts:
            return verdicts
    return []


@dataclass(frozen=True)
class AdvisorApplyResult:
    kept: list[ConvictionResult]
    skipped: list[tuple[ConvictionResult, TeamAdvisorVerdict]]
    multipliers: dict[str, float]


def apply_advisor_gates(
    results: list[ConvictionResult],
    verdicts: list[TeamAdvisorVerdict],
    *,
    gate: AdvisorGate,
) -> AdvisorApplyResult:
    """Apply advisory overlay — hard gate drops skips; reduce lowers notional only."""
    if gate == AdvisorGate.OFF or not verdicts:
        return AdvisorApplyResult(
            kept=[r for r in results if r.quote],
            skipped=[],
            multipliers={},
        )

    by_team = {v.team.lower(): v for v in verdicts}
    kept: list[ConvictionResult] = []
    skipped: list[tuple[ConvictionResult, TeamAdvisorVerdict]] = []
    multipliers: dict[str, float] = {}

    for result in results:
        if not result.quote:
            continue
        verdict = by_team.get(result.market.team.lower())
        if verdict is None:
            kept.append(result)
            continue

        block = verdict.verdict in {AdvisorVerdict.SKIP, AdvisorVerdict.HUMAN_REVIEW}
        if block and gate == AdvisorGate.HARD:
            skipped.append((result, verdict))
            continue

        if verdict.verdict == AdvisorVerdict.REDUCE or verdict.notional_multiplier < 1.0:
            multipliers[result.market.team] = verdict.notional_multiplier

        kept.append(result)

    return AdvisorApplyResult(kept=kept, skipped=skipped, multipliers=multipliers)


class Advisor(Protocol):
    def review(self, context: DecisionContext) -> list[TeamAdvisorVerdict]: ...


class NoopAdvisor:
    """Default — no API calls, no cost."""

    def review(self, context: DecisionContext) -> list[TeamAdvisorVerdict]:
        _ = context
        return []


class OpenAICompatibleAdvisor:
    """Works with Ollama, LM Studio, OpenRouter, OpenAI, etc. (OpenAI chat schema)."""

    def __init__(self, settings: AdvisorSettings) -> None:
        if not settings.configured:
            raise AdvisorNotConfiguredError(
                "ADVISOR_BASE_URL is not set — see SETUP.md (advisor is optional)"
            )
        self._settings = settings

    def review(self, context: DecisionContext) -> list[TeamAdvisorVerdict]:
        system = context.advisor_instructions or _default_system_prompt()
        user = (
            "Review each team below for LP quoting today. "
            "Return ONLY a JSON array of verdict objects (see schema in instructions).\n\n"
            + json.dumps(context.to_dict(), indent=2)
        )
        text = _post_chat(
            base_url=self._settings.base_url or "",
            api_key=self._settings.api_key,
            model=self._settings.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            timeout_sec=self._settings.timeout_sec,
        )
        verdicts = parse_advisor_response(text)
        if not verdicts:
            logger.warning("advisor returned no parseable verdicts")
        return verdicts


class AdvisorNotConfiguredError(RuntimeError):
    pass


def load_advisor(settings: AdvisorSettings | None = None) -> Advisor:
    cfg = settings or AdvisorSettings.from_env()
    if not cfg.configured:
        raise AdvisorNotConfiguredError(
            "Set ADVISOR_BASE_URL to enable (e.g. http://localhost:11434/v1 for Ollama)"
        )
    return OpenAICompatibleAdvisor(cfg)


def _default_system_prompt() -> str:
    return (
        "You advise a Polymarket FIFA 2026 advance-to-knockout LP bot. "
        "You may only recommend skip, reduce size, or human_review — never increase "
        "notional above config caps. Return JSON array with team, verdict, confidence, "
        "notional_multiplier (0-1), reasons, risk_factors, signal_quality."
    )


def _post_chat(
    *,
    base_url: str,
    api_key: str | None,
    model: str,
    messages: list[dict[str, str]],
    timeout_sec: float,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({"model": model, "messages": messages, "temperature": 0.2}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        raise RuntimeError(f"advisor HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"advisor connection failed: {exc.reason}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("advisor returned empty choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("advisor returned empty content")
    return str(content)
