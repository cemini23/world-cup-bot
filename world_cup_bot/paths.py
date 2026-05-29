"""Project root resolution — config paths work regardless of shell cwd."""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def resolve_project_path(raw: str | Path) -> Path:
    """Resolve relative paths against the repo/package root (pip install -e friendly)."""
    p = Path(raw)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p
