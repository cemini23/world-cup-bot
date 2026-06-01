"""Windows-safe stdio helpers for CLI output."""

from __future__ import annotations

import sys


def configure_stdio() -> None:
    """Prefer UTF-8 on stdout/stderr so runtime Unicode does not crash cp1252 consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, LookupError, OSError, ValueError):
            pass


def write_stderr(text: str) -> None:
    """Write to stderr without raising UnicodeEncodeError on legacy Windows encodings."""
    try:
        sys.stderr.write(text)
    except UnicodeEncodeError:
        enc = sys.stderr.encoding or "ascii"
        sys.stderr.write(text.encode(enc, errors="replace").decode(enc, errors="replace"))
