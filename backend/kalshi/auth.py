"""Kalshi API authentication using RSA-PSS signatures.

Required environment variables (or hardcoded if testing):
- KALSHI_API_KEY_ID: Your API key ID from Kalshi dashboard
- KALSHI_PRIVATE_KEY_PATH: Path to private key .pem file
"""

import time
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_private_key():
    """Load RSA private key from PEM file."""
    key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "path/to/private_key.pem")
    # Resolve relative paths against project root
    if not os.path.isabs(key_path):
        key_path = str(PROJECT_ROOT / key_path)
    try:
        with open(key_path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Private key file not found at {key_path}. "
            "Set KALSHI_PRIVATE_KEY_PATH environment variable."
        )
    except Exception as e:
        raise ValueError(f"Failed to load private key: {e}")


def get_auth_headers(method: str, path: str) -> dict:
    """Generate Kalshi authentication headers for a request.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path WITHOUT query string (e.g. "/trade-api/v2/portfolio/orders")

    Returns:
        dict with KALSHI-ACCESS-* headers
    """
    api_key_id = os.getenv("KALSHI_API_KEY_ID", "")
    if not api_key_id or api_key_id in ("your_api_key_id", "YOUR_API_KEY_ID"):
        raise ValueError(
            "KALSHI_API_KEY_ID is not set. "
            "Update your .env file with your real API key ID from the Kalshi dashboard."
        )
    timestamp_ms = str(int(time.time() * 1000))
    msg = (timestamp_ms + method.upper() + path).encode()

    private_key = load_private_key()
    signature = private_key.sign(
        msg,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )

    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "Content-Type": "application/json",
    }
