"""CLOB L2 API credentials for authenticated WebSocket / REST (not Builder keys)."""

from __future__ import annotations

import os
from dataclasses import dataclass


class MissingClobAuthError(RuntimeError):
    """Raised when L2 API credentials are required but not configured."""


@dataclass(frozen=True)
class ClobAuth:
    api_key: str
    secret: str
    passphrase: str

    def subscription_fields(self) -> dict[str, str]:
        return {
            "apiKey": self.api_key,
            "secret": self.secret,
            "passphrase": self.passphrase,
        }


def clob_auth_configured() -> bool:
    """True when all three L2 env vars are set."""
    return all(
        os.environ.get(name, "").strip()
        for name in (
            "POLYMARKET_API_KEY",
            "POLYMARKET_API_SECRET",
            "POLYMARKET_API_PASSPHRASE",
        )
    )


def load_clob_auth() -> ClobAuth:
    """Load L2 creds from env — derive once via py-clob-client or Polymarket settings."""
    api_key = os.environ.get("POLYMARKET_API_KEY", "").strip()
    secret = os.environ.get("POLYMARKET_API_SECRET", "").strip()
    passphrase = os.environ.get("POLYMARKET_API_PASSPHRASE", "").strip()
    missing = [
        name
        for name, val in (
            ("POLYMARKET_API_KEY", api_key),
            ("POLYMARKET_API_SECRET", secret),
            ("POLYMARKET_API_PASSPHRASE", passphrase),
        )
        if not val
    ]
    if missing:
        raise MissingClobAuthError(
            "Missing CLOB L2 credentials: "
            + ", ".join(missing)
            + ". Derive from POLYMARKET_PRIVATE_KEY via py-clob-client "
            "create_or_derive_api_creds()."
        )
    return ClobAuth(api_key=api_key, secret=secret, passphrase=passphrase)


def load_poly_address() -> str:
    """Signer address for L2 POLY_ADDRESS header."""
    explicit = os.environ.get("POLYMARKET_POLY_ADDRESS", "").strip()
    if explicit:
        return explicit
    pk = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if pk:
        try:
            from eth_account import Account
        except ImportError as exc:
            raise MissingClobAuthError(
                "Set POLYMARKET_POLY_ADDRESS or pip install -e '.[live]' (eth-account)"
            ) from exc
        return Account.from_key(pk).address
    raise MissingClobAuthError(
        "POLYMARKET_POLY_ADDRESS or POLYMARKET_PRIVATE_KEY required for L2 REST"
    )


def load_maker_address() -> str:
    """Funder/proxy address for GET /data/trades maker filter."""
    funder = os.environ.get("POLYMARKET_FUNDER_ADDRESS", "").strip()
    if funder:
        return funder
    return load_poly_address()
