"""Polymarket trading module using the py-clob-client SDK.

Uses the official SDK for order signing (EIP-712) and submission.
Falls back to raw REST API if SDK is unavailable.

Required environment variables:
- POLY_PRIVATE_KEY: Ethereum private key
- POLY_API_KEY, POLY_API_SECRET, POLY_PASSPHRASE: API credentials
- POLY_FUNDER_ADDRESS: Wallet address holding funds
"""

import os
import json
import requests
from polymarket.auth import (
    get_l2_headers,
    POLY_PRIVATE_KEY,
    POLY_API_KEY,
    POLY_API_SECRET,
    POLY_PASSPHRASE,
    POLY_FUNDER_ADDRESS,
    POLY_SIGNATURE_TYPE,
)

BASE_URL = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet

# Polymarket fee schedule per market category.
# Formula: fee_shares = C * p * fee_rate * (p * (1 - p)) ^ exponent
# where C = shares traded, p = price per share.
# See https://docs.polymarket.com/trading/fees
POLY_FEE_SCHEDULES = {
    "crypto": {"fee_rate": 0.25, "exponent": 2, "maker_rebate": 0.20},
    "sports": {"fee_rate": 0.0175, "exponent": 1, "maker_rebate": 0.25},
}


def calculate_poly_fee(
    price: float,
    size: float,
    category: str = "crypto",
    is_maker: bool = False,
) -> float:
    """Calculate Polymarket taker fee for a trade.

    For BUY orders the fee is denominated in shares (reducing shares received).
    For the purpose of arbitrage P&L we return the fee in USD-equivalent terms
    (fee_shares * $1 payout), which equals the raw fee_shares value.

    Args:
        price: Share price (0 < p < 1)
        size: Number of shares
        category: Fee schedule key ("crypto" or "sports")
        is_maker: If True, returns 0 (makers pay no fee)

    Returns:
        Fee amount in USD-equivalent terms (reduces profit by this amount per share)
    """
    if is_maker:
        return 0.0

    schedule = POLY_FEE_SCHEDULES.get(category)
    if schedule is None:
        return 0.0

    p = price
    fee = size * p * schedule["fee_rate"] * (p * (1 - p)) ** schedule["exponent"]
    return max(fee, 0.0)

# Try to import the official SDK
try:
    from py_clob_client.client import ClobClient
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


def _get_sdk_client():
    """Create and return a configured ClobClient instance.

    Returns:
        ClobClient or None if credentials are missing
    """
    if not SDK_AVAILABLE:
        return None
    if not all([POLY_PRIVATE_KEY, POLY_API_KEY, POLY_API_SECRET, POLY_PASSPHRASE]):
        return None

    from py_clob_client.clob_types import ApiCreds

    creds = ApiCreds(
        api_key=POLY_API_KEY,
        api_secret=POLY_API_SECRET,
        api_passphrase=POLY_PASSPHRASE,
    )

    return ClobClient(
        BASE_URL,
        key=POLY_PRIVATE_KEY,
        chain_id=CHAIN_ID,
        creds=creds,
        signature_type=POLY_SIGNATURE_TYPE,
        funder=POLY_FUNDER_ADDRESS,
    )


def place_order(
    token_id: str,
    side: str,
    price: float,
    size: float,
    tick_size: str = "0.01",
    neg_risk: bool = False,
    order_type: str = "GTC",
    dry_run: bool = False,
) -> dict:
    """Place an order on Polymarket.

    Args:
        token_id: CLOB token ID for the outcome
        side: "BUY" or "SELL"
        price: Price per share (0.0 to 1.0)
        size: Number of shares
        tick_size: Market tick size ("0.1", "0.01", "0.001", "0.0001")
        neg_risk: Whether this is a neg-risk market
        order_type: "GTC", "GTD", "FOK", or "FAK"
        dry_run: If True, log but don't actually place

    Returns:
        dict with keys: success, order_id, error
    """
    side_upper = side.upper()
    if side_upper not in ("BUY", "SELL"):
        return {
            "success": False,
            "order_id": None,
            "error": f"Invalid side '{side}'. Must be 'BUY' or 'SELL'",
        }

    if price <= 0 or price >= 1:
        return {
            "success": False,
            "order_id": None,
            "error": f"Price {price} outside valid range (0, 1)",
        }

    if size <= 0:
        return {
            "success": False,
            "order_id": None,
            "error": f"Size must be positive, got {size}",
        }

    if dry_run:
        print(
            f"[DRY RUN] Polymarket order: {side_upper} {size} @ {price} "
            f"token={token_id[:16]}..."
        )
        return {
            "success": True,
            "order_id": f"SIMULATED_POLY_{token_id[:8]}",
            "error": None,
        }

    # Use SDK if available (handles EIP-712 signing)
    if SDK_AVAILABLE:
        return _place_order_sdk(token_id, side_upper, price, size,
                                tick_size, neg_risk, order_type)
    else:
        return {
            "success": False,
            "order_id": None,
            "error": (
                "py-clob-client SDK not installed. "
                "Run: pip install py-clob-client"
            ),
        }


def _place_order_sdk(token_id: str, side: str, price: float, size: float,
                     tick_size: str, neg_risk: bool, order_type: str) -> dict:
    """Place order using the official py-clob-client SDK."""
    client = _get_sdk_client()
    if client is None:
        return {
            "success": False,
            "order_id": None,
            "error": "Missing Polymarket credentials. Check env vars.",
        }

    try:
        from py_clob_client.clob_types import OrderArgs, OrderType as OT
        from py_clob_client.order_builder.constants import BUY as SDK_BUY, SELL as SDK_SELL

        sdk_side = SDK_BUY if side == "BUY" else SDK_SELL
        sdk_order_type = getattr(OT, order_type, OT.GTC)

        resp = client.create_and_post_order(
            OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=sdk_side,
            ),
            options={"tick_size": tick_size, "neg_risk": neg_risk},
            order_type=sdk_order_type,
        )

        if resp.get("success"):
            return {
                "success": True,
                "order_id": resp.get("orderID"),
                "error": None,
            }
        else:
            return {
                "success": False,
                "order_id": None,
                "error": resp.get("errorMsg", "Unknown SDK error"),
            }
    except Exception as e:
        return {
            "success": False,
            "order_id": None,
            "error": str(e),
        }


def get_order_status(order_id: str) -> dict:
    """Get status of an order by ID.

    Args:
        order_id: Order ID/hash

    Returns:
        dict with keys: success, data, error
    """
    path = f"/order/{order_id}"
    try:
        headers = get_l2_headers("GET", path)
        resp = requests.get(BASE_URL + path, headers=headers, timeout=10)

        if resp.status_code == 200:
            return {"success": True, "data": resp.json(), "error": None}
        else:
            return {
                "success": False,
                "data": None,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except Exception as e:
        return {"success": False, "data": None, "error": str(e)}


def get_open_orders() -> dict:
    """Fetch all open/live orders.

    Returns:
        dict with keys: success, orders (list), total_cost_usdc (float), error
    """
    path = "/data/orders"
    try:
        headers = get_l2_headers("GET", path)
        resp = requests.get(
            BASE_URL + path,
            params={"state": "live"},
            headers=headers,
            timeout=10,
        )

        if resp.status_code == 200:
            orders = resp.json()
            if not isinstance(orders, list):
                orders = orders.get("orders", [])
            # Sum up cost: price * remaining size
            total_cost_usdc = 0.0
            for o in orders:
                price = float(o.get("price", "0"))
                original = float(o.get("original_size", "0"))
                matched = float(o.get("size_matched", "0"))
                remaining = original - matched
                total_cost_usdc += price * remaining
            return {
                "success": True,
                "orders": orders,
                "total_cost_usdc": total_cost_usdc,
                "error": None,
            }
        else:
            return {
                "success": False,
                "orders": [],
                "total_cost_usdc": 0.0,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except Exception as e:
        return {"success": False, "orders": [], "total_cost_usdc": 0.0, "error": str(e)}


def cancel_order(order_id: str, dry_run: bool = False) -> dict:
    """Cancel an order.

    Args:
        order_id: Order ID/hash to cancel
        dry_run: If True, log but don't actually cancel

    Returns:
        dict with keys: success, error
    """
    if dry_run:
        print(f"[DRY RUN] Would cancel Polymarket order {order_id}")
        return {"success": True, "error": None}

    path = "/order"
    body = json.dumps({"orderID": order_id})
    try:
        headers = get_l2_headers("DELETE", path, body)
        resp = requests.delete(BASE_URL + path, headers=headers,
                               data=body, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            if order_id in data.get("canceled", []):
                return {"success": True, "error": None}
            not_canceled = data.get("not_canceled", {})
            if order_id in not_canceled:
                return {"success": False, "error": not_canceled[order_id]}
            return {"success": True, "error": None}
        else:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _query_onchain_usdc_balance(address: str) -> int | None:
    """Query USDC balance on Polygon for a given address. Returns raw units (6 decimals) or None on failure."""
    USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    addr = address.lower().replace("0x", "").zfill(64)
    data = "0x70a08231" + addr
    payload = {"jsonrpc": "2.0", "method": "eth_call", "params": [{"to": USDC_CONTRACT, "data": data}, "latest"], "id": 1}
    try:
        resp = requests.post("https://polygon-bor-rpc.publicnode.com", json=payload, timeout=5)
        result = resp.json().get("result")
        if result:
            return int(result, 16)
    except Exception:
        pass
    return None


def get_balance() -> dict:
    """Get balance and allowance info.

    Returns:
        dict with keys: success, data, error
    """
    if not SDK_AVAILABLE:
        return {
            "success": False,
            "data": None,
            "error": "py-clob-client SDK not installed",
        }

    client = _get_sdk_client()
    if client is None:
        return {
            "success": False,
            "data": None,
            "error": "Missing Polymarket credentials",
        }

    try:
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=POLY_SIGNATURE_TYPE,
        )
        data = client.get_balance_allowance(params)

        # The SDK queries the EOA address, but with Gnosis Safe (signature_type=1)
        # funds are held by the funder/proxy wallet. Query on-chain if SDK returns 0.
        if POLY_FUNDER_ADDRESS and data.get("balance") == "0":
            onchain = _query_onchain_usdc_balance(POLY_FUNDER_ADDRESS)
            if onchain is not None:
                data["balance"] = str(onchain)
                data["source"] = "onchain_funder"

        return {"success": True, "data": data, "error": None}
    except Exception as e:
        return {"success": False, "data": None, "error": str(e)}
