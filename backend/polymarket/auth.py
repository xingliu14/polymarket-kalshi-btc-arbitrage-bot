"""Polymarket CLOB API authentication.

Required environment variables:
- POLY_PRIVATE_KEY: Ethereum private key for signing orders
- POLY_API_KEY: API key from create_or_derive_api_creds()
- POLY_API_SECRET: API secret from create_or_derive_api_creds()
- POLY_PASSPHRASE: Passphrase from create_or_derive_api_creds()
- POLY_FUNDER_ADDRESS: Wallet address holding trading funds
"""

import os
import time
import hmac
import hashlib
import base64

POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")
POLY_API_KEY = os.getenv("POLY_API_KEY", "")
POLY_API_SECRET = os.getenv("POLY_API_SECRET", "")
POLY_PASSPHRASE = os.getenv("POLY_PASSPHRASE", "")
POLY_FUNDER_ADDRESS = os.getenv("POLY_FUNDER_ADDRESS", "")

# Signature type: 0 = EOA, 1 = Poly Gnosis Safe, 2 = Poly Gnosis Safe (old)
POLY_SIGNATURE_TYPE = int(os.getenv("POLY_SIGNATURE_TYPE", "0"))


def build_hmac_signature(secret: str, timestamp: str, method: str,
                         request_path: str, body: str = None) -> str:
    """Build HMAC-SHA256 signature for Polymarket L2 auth.

    Matches the official py-clob-client implementation.

    Args:
        secret: Base64-encoded API secret
        timestamp: Unix timestamp string
        method: HTTP method (GET, POST, DELETE)
        request_path: Request path (e.g., "/order")
        body: JSON body string (optional)

    Returns:
        Base64-encoded HMAC signature
    """
    decoded_secret = base64.urlsafe_b64decode(secret)
    message = timestamp + method + request_path
    if body:
        message += body.replace("'", '"')

    h = hmac.new(decoded_secret, message.encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(h.digest()).decode("utf-8")


def get_l2_headers(method: str, request_path: str,
                   body: str = None) -> dict:
    """Generate Polymarket L2 authentication headers.

    Args:
        method: HTTP method (GET, POST, DELETE)
        request_path: Request path (e.g., "/order")
        body: JSON body string (optional)

    Returns:
        dict with POLY_* headers
    """
    timestamp = str(int(time.time()))
    signature = build_hmac_signature(
        POLY_API_SECRET, timestamp, method, request_path, body
    )

    return {
        "POLY_ADDRESS": POLY_FUNDER_ADDRESS,
        "POLY_SIGNATURE": signature,
        "POLY_TIMESTAMP": timestamp,
        "POLY_API_KEY": POLY_API_KEY,
        "POLY_PASSPHRASE": POLY_PASSPHRASE,
        "Content-Type": "application/json",
    }
