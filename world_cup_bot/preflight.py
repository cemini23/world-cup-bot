"""Pre-flight checks before live LP — geoblock, Gamma, CLOB auth."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum

from world_cup_bot.clob_auth import ClobAuth, MissingClobAuthError, load_clob_auth
from world_cup_bot.clob_rest import (
    fetch_clob_time,
    fetch_geoblock,
    fetch_open_orders,
    probe_clob_burst,
)
from world_cup_bot.config import Settings
from world_cup_bot.scanner import fetch_search_payload


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: CheckStatus
    detail: str


@dataclass
class PreflightReport:
    checks: list[PreflightCheck] = field(default_factory=list)
    ok: bool = True

    def add(self, check: PreflightCheck) -> None:
        self.checks.append(check)
        if check.status == CheckStatus.FAIL:
            self.ok = False


def _load_poly_address() -> str | None:
    explicit = os.environ.get("POLYMARKET_POLY_ADDRESS", "").strip()
    if explicit:
        return explicit
    pk = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if not pk:
        return None
    try:
        from eth_account import Account
    except ImportError:
        return None
    return Account.from_key(pk).address


def _load_maker_address(poly_address: str | None) -> str | None:
    funder = os.environ.get("POLYMARKET_FUNDER_ADDRESS", "").strip()
    return funder or poly_address


def run_preflight(settings: Settings, *, test_auth: bool = True) -> PreflightReport:
    report = PreflightReport()

    # DRY_RUN posture
    if settings.dry_run:
        report.add(
            PreflightCheck(
                "dry_run",
                CheckStatus.WARN,
                "DRY_RUN=true — live POST disabled; set DRY_RUN=false for LP",
            )
        )
    else:
        report.add(
            PreflightCheck("dry_run", CheckStatus.PASS, "DRY_RUN=false — live mode requested")
        )

    # Geoblock
    try:
        geo = fetch_geoblock()
        if geo.blocked:
            status = CheckStatus.FAIL if not settings.dry_run else CheckStatus.WARN
            report.add(
                PreflightCheck(
                    "geoblock",
                    status,
                    f"Order POST blocked from {geo.country}/{geo.region} ({geo.ip}) "
                    "— use non-US egress for live LP",
                )
            )
        else:
            report.add(
                PreflightCheck(
                    "geoblock",
                    CheckStatus.PASS,
                    f"Trading allowed from {geo.country}/{geo.region} ({geo.ip})",
                )
            )
    except Exception as exc:
        report.add(
            PreflightCheck("geoblock", CheckStatus.WARN, f"Could not reach geoblock API: {exc}")
        )

    # Gamma public-search
    try:
        payload = fetch_search_payload(
            settings.gamma_url,
            "FIFA World Cup 2026 advance knockout",
        )
        events = len(payload.get("events") or [])
        report.add(
            PreflightCheck(
                "gamma",
                CheckStatus.PASS if events else CheckStatus.WARN,
                f"Gamma public-search OK ({events} events)",
            )
        )
    except Exception as exc:
        report.add(PreflightCheck("gamma", CheckStatus.FAIL, f"Gamma unreachable: {exc}"))

    # CLOB /time (public)
    try:
        ts = fetch_clob_time(settings.clob_url)
        report.add(
            PreflightCheck(
                "clob_time",
                CheckStatus.PASS if ts > 0 else CheckStatus.WARN,
                f"CLOB /time → {ts}",
            )
        )
    except Exception as exc:
        report.add(PreflightCheck("clob_time", CheckStatus.WARN, f"CLOB /time failed: {exc}"))

    # Burst probe — shadow-to-live 429 preflight (clob-rate-limit-mitigation wiki)
    try:
        burst = probe_clob_burst(settings.clob_url, count=5)
        if burst.rate_limited > 0:
            status = CheckStatus.FAIL if not settings.dry_run else CheckStatus.WARN
            report.add(
                PreflightCheck(
                    "clob_rate_limit",
                    status,
                    f"CLOB burst probe: {burst.rate_limited}/{burst.requests} returned 429",
                )
            )
        else:
            hdr = f" headers={burst.sample_headers}" if burst.sample_headers else ""
            report.add(
                PreflightCheck(
                    "clob_rate_limit",
                    CheckStatus.PASS,
                    f"CLOB burst probe OK ({burst.successes}/{burst.requests} OK){hdr}",
                )
            )
    except Exception as exc:
        report.add(
            PreflightCheck(
                "clob_rate_limit",
                CheckStatus.WARN,
                f"CLOB burst probe failed: {exc}",
            )
        )

    # Private key for live POST
    pk = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if settings.dry_run:
        report.add(
            PreflightCheck(
                "private_key",
                CheckStatus.SKIP if not pk else CheckStatus.PASS,
                "Skipped (shadow mode)" if not pk else "POLYMARKET_PRIVATE_KEY set",
            )
        )
    elif not pk:
        report.add(
            PreflightCheck(
                "private_key",
                CheckStatus.FAIL,
                "POLYMARKET_PRIVATE_KEY missing — required for live POST",
            )
        )
    else:
        report.add(PreflightCheck("private_key", CheckStatus.PASS, "POLYMARKET_PRIVATE_KEY set"))

    poly_address = _load_poly_address()
    maker_address = _load_maker_address(poly_address)

    # L2 creds + authenticated GET /data/orders
    auth: ClobAuth | None = None
    try:
        auth = load_clob_auth()
        report.add(PreflightCheck("l2_creds", CheckStatus.PASS, "L2 API credentials present"))
    except MissingClobAuthError as exc:
        if test_auth:
            report.add(
                PreflightCheck(
                    "l2_creds",
                    CheckStatus.WARN if settings.dry_run else CheckStatus.FAIL,
                    str(exc),
                )
            )

    if test_auth and auth and poly_address:
        try:
            orders = fetch_open_orders(settings.clob_url, auth, poly_address, max_pages=1)
            report.add(
                PreflightCheck(
                    "clob_auth",
                    CheckStatus.PASS,
                    f"GET /data/orders OK ({len(orders)} open on first page)",
                )
            )
        except Exception as exc:
            report.add(
                PreflightCheck(
                    "clob_auth",
                    CheckStatus.FAIL,
                    f"L2 auth / orders failed: {exc}",
                )
            )
    elif test_auth and auth and not poly_address:
        report.add(
            PreflightCheck(
                "clob_auth",
                CheckStatus.WARN,
                "Set POLYMARKET_POLY_ADDRESS or install eth-account to test L2 GET /data/orders",
            )
        )
    elif test_auth and not auth:
        report.add(
            PreflightCheck(
                "clob_auth",
                CheckStatus.SKIP,
                "No L2 creds — skip authenticated CLOB test",
            )
        )

    if maker_address:
        report.add(
            PreflightCheck(
                "maker_address",
                CheckStatus.PASS,
                f"Reconcile maker_address={maker_address[:10]}…",
            )
        )
    elif not settings.dry_run:
        report.add(
            PreflightCheck(
                "maker_address",
                CheckStatus.WARN,
                "POLYMARKET_FUNDER_ADDRESS unset — reconcile uses POLY_ADDRESS only",
            )
        )

    # py-clob-client-v2 for live POST (V1 archived Apr 2026 — order_version_mismatch)
    if not settings.dry_run:
        try:
            import py_clob_client_v2  # noqa: F401

            report.add(
                PreflightCheck(
                    "py_clob_client_v2",
                    CheckStatus.PASS,
                    "py-clob-client-v2 installed",
                )
            )
            report.add(
                PreflightCheck(
                    "py_clob_client",
                    CheckStatus.PASS,
                    "alias: py-clob-client-v2 (V1 deprecated)",
                )
            )
        except ImportError:
            report.add(
                PreflightCheck(
                    "py_clob_client_v2",
                    CheckStatus.FAIL,
                    "pip install -e '.[live]' required for live POST (py-clob-client-v2)",
                )
            )

    return report
