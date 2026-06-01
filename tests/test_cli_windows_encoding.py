"""Windows cp1252 console compatibility (help text + UI banner)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from world_cup_bot import __main__ as cli_main


def _walk_parser_help(parser: argparse.ArgumentParser, non_ascii: list[str]) -> None:
    for action in parser._actions:
        help_text = action.help
        if help_text and not help_text.isascii():
            non_ascii.append(f"{action.dest}: {help_text!r}")
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                _walk_parser_help(sub, non_ascii)


def test_help_decodes_as_cp1252():
    proc = subprocess.run(
        [sys.executable, "-m", "world_cup_bot", "--help"],
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    # Simulates default Windows console encoding for argparse help output.
    proc.stdout.decode("cp1252")


def test_argparse_help_strings_are_ascii():
    non_ascii: list[str] = []
    _walk_parser_help(cli_main.build_parser(), non_ascii)
    assert not non_ascii, "Non-ASCII argparse help (breaks cp1252 --help):\n" + "\n".join(non_ascii)


def test_threshold_guard_python_entrypoint():
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_hardcoded_thresholds.py"
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, check=False)
    assert proc.returncode == 0
    assert b"OK:" in proc.stdout


def test_ui_startup_banner_is_ascii():
    url = "http://localhost:8765/"
    banner = f"World Cup Bot UI (read-only) -> {url}\n"
    banner.encode("cp1252")
