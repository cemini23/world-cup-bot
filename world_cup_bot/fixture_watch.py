"""Fixture refresh — diff vendored openfootball JSON vs upstream (alert-only)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot.calendar_guard import DEFAULT_FIXTURES, parse_kickoff_utc
from world_cup_bot.http_client import urlopen_get

DEFAULT_UPSTREAM_URL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
)


@dataclass(frozen=True)
class FixtureChange:
    change_type: str  # added | removed | rescheduled
    team1: str
    team2: str
    group: str
    old_kickoff_utc: str | None
    new_kickoff_utc: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type,
            "team1": self.team1,
            "team2": self.team2,
            "group": self.group,
            "old_kickoff_utc": self.old_kickoff_utc,
            "new_kickoff_utc": self.new_kickoff_utc,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class FixtureCheckResult:
    local_path: Path
    upstream_url: str
    local_sha256: str
    upstream_sha256: str
    local_match_count: int
    upstream_match_count: int
    changes: tuple[FixtureChange, ...]
    checked_at: str

    @property
    def has_changes(self) -> bool:
        return bool(self.changes) or self.local_sha256 != self.upstream_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at,
            "local_path": str(self.local_path),
            "upstream_url": self.upstream_url,
            "local_sha256": self.local_sha256,
            "upstream_sha256": self.upstream_sha256,
            "local_match_count": self.local_match_count,
            "upstream_match_count": self.upstream_match_count,
            "has_changes": self.has_changes,
            "changes": [c.to_dict() for c in self.changes],
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_upstream_fixtures(
    url: str = DEFAULT_UPSTREAM_URL,
    *,
    timeout: float = 30,
) -> dict[str, Any]:
    with urlopen_get(url, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    if not isinstance(payload, dict):
        raise ValueError("upstream fixtures payload is not a JSON object")
    return payload


def _match_key(match: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(match.get("date") or ""),
        str(match.get("team1") or ""),
        str(match.get("team2") or ""),
        str(match.get("group") or ""),
    )


def _kickoff_iso(match: dict[str, Any]) -> str | None:
    date = match.get("date")
    time = match.get("time")
    if not date or not time:
        return None
    try:
        return parse_kickoff_utc(str(date), str(time)).isoformat()
    except ValueError:
        return None


def diff_fixtures(local: dict[str, Any], upstream: dict[str, Any]) -> list[FixtureChange]:
    local_matches = local.get("matches") or []
    upstream_matches = upstream.get("matches") or []

    local_by_key = {_match_key(m): m for m in local_matches if isinstance(m, dict)}
    upstream_by_key = {_match_key(m): m for m in upstream_matches if isinstance(m, dict)}

    changes: list[FixtureChange] = []

    for key, remote in upstream_by_key.items():
        if key not in local_by_key:
            changes.append(
                FixtureChange(
                    change_type="added",
                    team1=str(remote.get("team1") or ""),
                    team2=str(remote.get("team2") or ""),
                    group=str(remote.get("group") or ""),
                    old_kickoff_utc=None,
                    new_kickoff_utc=_kickoff_iso(remote),
                    detail="match present upstream but not in local vendored file",
                )
            )

    for key, local_m in local_by_key.items():
        if key not in upstream_by_key:
            changes.append(
                FixtureChange(
                    change_type="removed",
                    team1=str(local_m.get("team1") or ""),
                    team2=str(local_m.get("team2") or ""),
                    group=str(local_m.get("group") or ""),
                    old_kickoff_utc=_kickoff_iso(local_m),
                    new_kickoff_utc=None,
                    detail="match in local file but removed upstream",
                )
            )

    for key in set(local_by_key) & set(upstream_by_key):
        local_m = local_by_key[key]
        remote_m = upstream_by_key[key]
        time_changed = local_m.get("time") != remote_m.get("time")
        date_changed = local_m.get("date") != remote_m.get("date")
        if time_changed or date_changed:
            changes.append(
                FixtureChange(
                    change_type="rescheduled",
                    team1=str(local_m.get("team1") or ""),
                    team2=str(local_m.get("team2") or ""),
                    group=str(local_m.get("group") or ""),
                    old_kickoff_utc=_kickoff_iso(local_m),
                    new_kickoff_utc=_kickoff_iso(remote_m),
                    detail=(
                        f"kickoff {local_m.get('date')} {local_m.get('time')} → "
                        f"{remote_m.get('date')} {remote_m.get('time')}"
                    ),
                )
            )

    return changes


def check_fixtures(
    *,
    local_path: Path | None = None,
    upstream_url: str = DEFAULT_UPSTREAM_URL,
) -> FixtureCheckResult:
    path = local_path or DEFAULT_FIXTURES
    local_bytes = path.read_bytes()
    local_data = json.loads(local_bytes.decode())
    upstream_data = fetch_upstream_fixtures(upstream_url)
    upstream_bytes = json.dumps(upstream_data, sort_keys=True).encode()

    changes = diff_fixtures(local_data, upstream_data)
    return FixtureCheckResult(
        local_path=path,
        upstream_url=upstream_url,
        local_sha256=_sha256_bytes(local_bytes),
        upstream_sha256=_sha256_bytes(upstream_bytes),
        local_match_count=len(local_data.get("matches") or []),
        upstream_match_count=len(upstream_data.get("matches") or []),
        changes=tuple(changes),
        checked_at=datetime.now(UTC).isoformat(),
    )


def apply_upstream_fixtures(
    *,
    local_path: Path | None = None,
    upstream_url: str = DEFAULT_UPSTREAM_URL,
) -> Path:
    """Replace vendored fixtures with upstream JSON (operator-initiated refresh)."""
    path = local_path or DEFAULT_FIXTURES
    upstream = fetch_upstream_fixtures(upstream_url)
    path.write_text(json.dumps(upstream, indent=1) + "\n", encoding="utf-8")
    return path
