"""Polymarket CLOB L2 HMAC signing (stdlib — matches py-clob-client)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

from world_cup_bot.clob_auth import ClobAuth

POLY_ADDRESS = "POLY_ADDRESS"
POLY_SIGNATURE = "POLY_SIGNATURE"
POLY_TIMESTAMP = "POLY_TIMESTAMP"
POLY_API_KEY = "POLY_API_KEY"
POLY_PASSPHRASE = "POLY_PASSPHRASE"


def build_hmac_signature(
    secret: str,
    timestamp: str,
    method: str,
    request_path: str,
    body: Any = None,
) -> str:
    """Sign request path + optional body with API secret (urlsafe base64)."""
    base64_secret = base64.urlsafe_b64decode(secret)
    message = str(timestamp) + str(method) + str(request_path)
    if body:
        message += str(body).replace("'", '"')
    digest = hmac.new(base64_secret, message.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def create_level_2_headers(
    auth: ClobAuth,
    *,
    address: str,
    method: str,
    request_path: str,
    body: Any = None,
    serialized_body: str | None = None,
    timestamp: int | None = None,
) -> dict[str, str]:
    ts = int(time.time()) if timestamp is None else timestamp
    body_for_sig = serialized_body if serialized_body is not None else body
    return {
        POLY_ADDRESS: address,
        POLY_SIGNATURE: build_hmac_signature(
            auth.secret, str(ts), method, request_path, body_for_sig
        ),
        POLY_TIMESTAMP: str(ts),
        POLY_API_KEY: auth.api_key,
        POLY_PASSPHRASE: auth.passphrase,
    }
