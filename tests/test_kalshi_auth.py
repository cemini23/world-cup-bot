"""Kalshi auth signing tests."""

from __future__ import annotations

from world_cup_bot.kalshi_auth import SIGN_PATH_PREFIX, KalshiAuth


def test_kalshi_sign_headers_shape():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    auth = KalshiAuth(api_key_id="test-key", private_key_pem=pem)
    headers = auth.sign(
        method="POST",
        path=f"{SIGN_PATH_PREFIX}/portfolio/orders",
        timestamp_ms="1700000000000",
    )
    assert headers["KALSHI-ACCESS-KEY"] == "test-key"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000000"
    assert len(headers["KALSHI-ACCESS-SIGNATURE"]) > 20
