"""Stage Gemini DR JSON as conviction YAML snippets — human merge only, never auto-apply."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

VALID_POSTURES = frozenset({"quote", "reduce", "skip", "human_review"})


@dataclass(frozen=True)
class ConvictionPatch:
    team: str
    mode: str | None
    max_notional_usd: float | None
    notes: str | None
    source: str

    def yaml_block(self) -> str:
        lines = [f"  {self.team}:"]
        if self.mode:
            lines.append(f"    mode: {self.mode}")
        if self.max_notional_usd is not None:
            lines.append(f"    max_notional_usd: {self.max_notional_usd:.0f}")
        if self.notes:
            lines.append(f"    # DR note: {self.notes}")
        return "\n".join(lines)


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    candidates: list[str] = [text.strip()]
    candidates.extend(m.group(1).strip() for m in _JSON_BLOCK.finditer(text))
    out: list[dict[str, Any]] = []
    for raw in candidates:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(data)
        elif isinstance(data, list):
            out.extend(x for x in data if isinstance(x, dict))
    return out


def _posture_to_mode(posture: str) -> tuple[str | None, float | None]:
    p = posture.strip().lower()
    if p == "quote":
        return None, None
    if p == "reduce":
        return None, None  # cap handled via max_notional multiplier separately
    if p in VALID_POSTURES:
        return p, None
    return "human_review", None


def patch_from_dr_object(obj: dict[str, Any], *, source: str = "dr_json") -> ConvictionPatch | None:
    team = obj.get("team")
    if not team:
        return None

    posture = (
        obj.get("lp_posture")
        or obj.get("verdict")
        or obj.get("posture")
        or obj.get("conviction_mode")
    )
    mode: str | None = None
    max_notional: float | None = None
    notes: str | None = None

    if posture:
        mode, _ = _posture_to_mode(str(posture))
        if str(posture).lower() == "reduce":
            mult = obj.get("notional_multiplier")
            if mult is not None:
                notes = f"reduce — apply notional_multiplier {mult} manually"
            else:
                notes = "reduce — set max_notional_usd in YAML"

    if obj.get("mode"):
        mode = str(obj["mode"]).lower()
    if obj.get("max_notional_usd") is not None:
        max_notional = float(obj["max_notional_usd"])
    elif obj.get("notional_cap_usd") is not None:
        max_notional = float(obj["notional_cap_usd"])

    review = obj.get("review_by")
    if review:
        notes = (notes + "; " if notes else "") + f"review_by {review}"

    if mode is None and max_notional is None and not notes:
        return None

    return ConvictionPatch(
        team=str(team),
        mode=mode,
        max_notional_usd=max_notional,
        notes=notes,
        source=source,
    )


def parse_dr_patches(text: str) -> list[ConvictionPatch]:
    patches: list[ConvictionPatch] = []
    seen: set[str] = set()
    for obj in _extract_json_objects(text):
        patch = patch_from_dr_object(obj)
        if patch is None or patch.team in seen:
            continue
        seen.add(patch.team)
        patches.append(patch)
    return patches


def render_staged_yaml(patches: list[ConvictionPatch]) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    header = (
        f"# STAGED conviction patch — generated {now}\n"
        "# Merge into config/conviction.yaml per_team: manually after review.\n"
        "# Do NOT commit blindly — DR can be wrong on injury/news.\n"
        "per_team:\n"
    )
    body = "\n".join(p.yaml_block() for p in patches)
    return header + body + "\n"


def stage_patches(
    patches: list[ConvictionPatch],
    *,
    out_dir: Path | None = None,
) -> Path:
    base = out_dir or Path("data/local/staged")
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = base / f"conviction-patch-{stamp}.yaml"
    path.write_text(render_staged_yaml(patches), encoding="utf-8")
    return path
