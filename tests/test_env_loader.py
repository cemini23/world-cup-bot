"""Tests for stdlib .env bootstrap."""

from __future__ import annotations

import os

from world_cup_bot.env_loader import bootstrap_env, load_dotenv_file


def test_load_dotenv_file_sets_missing_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("WC_TEST_DOTENV_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("WC_TEST_DOTENV_KEY=from_file\n", encoding="utf-8")
    load_dotenv_file(env_file)
    assert os.environ["WC_TEST_DOTENV_KEY"] == "from_file"


def test_load_dotenv_file_does_not_override_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_TEST_DOTENV_KEY", "existing")
    env_file = tmp_path / ".env"
    env_file.write_text("WC_TEST_DOTENV_KEY=from_file\n", encoding="utf-8")
    load_dotenv_file(env_file)
    assert os.environ["WC_TEST_DOTENV_KEY"] == "existing"


def test_bootstrap_env_skipped_when_flag_set(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_SKIP_DOTENV", "1")
    monkeypatch.delenv("WC_BOOTSTRAP_PROBE", raising=False)
    (tmp_path / ".env").write_text("WC_BOOTSTRAP_PROBE=loaded\n", encoding="utf-8")
    bootstrap_env(root=tmp_path)
    assert "WC_BOOTSTRAP_PROBE" not in os.environ
