"""Tests for CLOB L2 HMAC signing."""

import base64
import hashlib
import hmac

from world_cup_bot.clob_auth import ClobAuth
from world_cup_bot.clob_signing import build_hmac_signature, create_level_2_headers


def test_build_hmac_signature_matches_reference():
    secret = base64.urlsafe_b64encode(b"test-secret-key").decode()
    sig = build_hmac_signature(secret, "1700000000", "GET", "/data/orders")
    expected_msg = "1700000000GET/data/orders"
    key = base64.urlsafe_b64decode(secret)
    digest = hmac.new(key, expected_msg.encode(), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(digest).decode()
    assert sig == expected


def test_create_level_2_headers_shape():
    auth = ClobAuth(api_key="k", secret=base64.urlsafe_b64encode(b"s").decode(), passphrase="p")
    headers = create_level_2_headers(
        auth,
        address="0xabc",
        method="GET",
        request_path="/data/orders",
        timestamp=1700000000,
    )
    assert headers["POLY_API_KEY"] == "k"
    assert headers["POLY_PASSPHRASE"] == "p"
    assert headers["POLY_ADDRESS"] == "0xabc"
    assert headers["POLY_TIMESTAMP"] == "1700000000"
    assert headers["POLY_SIGNATURE"]
