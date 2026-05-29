"""Tests for project path resolution."""

from __future__ import annotations

from pathlib import Path

from world_cup_bot.config import Settings
from world_cup_bot.paths import PROJECT_ROOT, resolve_project_path


def test_project_root_has_config():
    assert (PROJECT_ROOT / "config" / "conviction.yaml").is_file()
    assert (PROJECT_ROOT / "config" / "strategy_logic_versions.yaml").is_file()


def test_resolve_project_path_relative():
    p = resolve_project_path("config/conviction.yaml")
    assert p.is_absolute()
    assert p.is_file()


def test_settings_from_any_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env()
    assert Path(settings.logic_version_config).is_file()
    assert Path(settings.conviction_config).is_file()
