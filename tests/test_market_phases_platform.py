"""Platform guards for market_phases helpers."""

from pathlib import Path

from world_cup_bot.market_phases import install_sigusr1_reload


def test_install_sigusr1_reload_no_crash_without_sigusr1(monkeypatch):
    monkeypatch.delattr("signal.SIGUSR1", raising=False)
    install_sigusr1_reload(Path("config/market_phases.yaml"))
