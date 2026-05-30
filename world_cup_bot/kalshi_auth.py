"""Kalshi RSA-PSS request signing (trade API v2)."""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path

SIGN_PATH_PREFIX = "/trade-api/v2"


class KalshiAuthError(RuntimeError):
    """Kalshi credentials missing or invalid."""


@dataclass(frozen=True)
class KalshiAuth:
    api_key_id: str
    private_key_pem: bytes

    def sign(self, *, method: str, path: str, timestamp_ms: str | None = None) -> dict[str, str]:
        ts = timestamp_ms or str(int(time.time() * 1000))
        sign_path = path if path.startswith(SIGN_PATH_PREFIX) else f"{SIGN_PATH_PREFIX}{path}"
        message = f"{ts}{method.upper()}{sign_path}".encode()
        signature = _sign_pss(self.private_key_pem, message)
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }


def _sign_pss(private_key_pem: bytes, message: bytes) -> str:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:
        raise KalshiAuthError("pip install -e '.[live]' for Kalshi signing (cryptography)") from exc

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    sig = key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("ascii")


def load_kalshi_auth() -> KalshiAuth:
    key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip()
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()
    if not key_id or not key_path:
        raise KalshiAuthError("KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH required")
    pem = Path(key_path).expanduser().read_bytes()
    if not pem.strip():
        raise KalshiAuthError(f"empty Kalshi private key: {key_path}")
    return KalshiAuth(api_key_id=key_id, private_key_pem=pem)


def kalshi_auth_configured() -> bool:
    return bool(
        os.environ.get("KALSHI_API_KEY_ID", "").strip()
        and os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()
    )


def authenticated_headers(
    auth: KalshiAuth,
    *,
    method: str,
    path: str,
    timestamp_ms: str | None = None,
) -> dict[str, str]:
    headers = auth.sign(method=method, path=path, timestamp_ms=timestamp_ms)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json"
    return headers
