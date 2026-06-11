"""Load repo-root .env into os.environ (stdlib-only; does not override existing vars)."""

from __future__ import annotations

import os
from pathlib import Path

from world_cup_bot.paths import PROJECT_ROOT


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_dotenv_file(path: Path, *, override: bool = False) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not override and key in os.environ:
            continue
        os.environ[key] = value


def bootstrap_env(*, root: Path | None = None) -> None:
    """Load `.env` (and optional Polymarket sidecar) before Settings.from_env()."""
    if _truthy("WC_SKIP_DOTENV"):
        return
    base = root or PROJECT_ROOT
    load_dotenv_file(base / ".env")
    if _truthy("WC_LOAD_POLYMARKET_ENV"):
        for name in (".env-polymarket", ".env.polymarket"):
            load_dotenv_file(base / name)
