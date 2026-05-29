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
