"""Kalshi trading module for placing and managing orders."""

import uuid
import requests
from kalshi.auth import get_auth_headers

BASE_URL = "https://api.elections.kalshi.com"
ORDERS_PATH = "/trade-api/v2/portfolio/orders"
BALANCE_PATH = "/trade-api/v2/portfolio/balance"


def calculate_kalshi_fee(
    price_cents: int,
    count: int,
    is_maker: bool = False,
) -> float:
    """Calculate Kalshi trading fee per the fee schedule (effective Feb 5, 2026).

    Taker: fees = round_up(0.07 × C × P × (1-P))
    Maker: fees = round_up(0.0175 × C × P × (1-P))

    Args:
        price_cents: Contract price in cents (1-99)
        count: Number of contracts
        is_maker: If True, use the lower maker fee rate

    Returns:
        Fee in dollars
    """
    # Use integer arithmetic to avoid floating point rounding errors.
    # rate_bps: taker=700, maker=175 (basis points * 100)
    rate_bps = 175 if is_maker else 700
    # raw_fee_cents * 1_000_000 = rate_bps * count * price_cents * (100 - price_cents)
    numerator = rate_bps * count * price_cents * (100 - price_cents)
    # Ceiling division to get fee in cents (rounded up)
    fee_cents = -(-numerator // 1_000_000)
    return fee_cents / 100.0


def place_order(
    ticker: str,
    side: str,
    action: str,
    count: int,
    yes_price_cents: int,
    dry_run: bool = False
) -> dict:
    """Place an order on Kalshi.

    Args:
        ticker: Market ticker (e.g., "KXBTCD-250326-14")
        side: "yes" or "no" - which side to buy
        action: "buy" or "sell"
        count: Number of contracts
        yes_price_cents: Price in cents (1-99)
        dry_run: If True, log but don't actually place

    Returns:
        dict with keys: success, order_id, client_order_id, error
    """
    client_order_id = str(uuid.uuid4())

    if yes_price_cents < 1 or yes_price_cents > 99:
        return {
            "success": False,
            "order_id": None,
            "client_order_id": client_order_id,
            "error": f"Price {yes_price_cents} outside 1-99 cent range"
        }

    payload = {
        "ticker": ticker,
        "action": action,
        "side": side,
        "count": count,
        "type": "limit",
        "yes_price": yes_price_cents,
        "client_order_id": client_order_id,
    }

    if dry_run:
        print(f"[DRY RUN] Would place order: {payload}")
        return {
            "success": True,
            "order_id": f"SIMULATED_{client_order_id[:8]}",
            "client_order_id": client_order_id,
            "error": None
        }

    try:
        headers = get_auth_headers("POST", ORDERS_PATH)
        resp = requests.post(BASE_URL + ORDERS_PATH, json=payload, headers=headers, timeout=10)

        if resp.status_code == 201:
            data = resp.json()
            order_id = data.get("order", {}).get("order_id")
            return {
                "success": True,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "error": None
            }
        else:
            return {
                "success": False,
                "order_id": None,
                "client_order_id": client_order_id,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
            }
    except Exception as e:
        return {
            "success": False,
            "order_id": None,
            "client_order_id": client_order_id,
            "error": str(e)
        }


def get_balance() -> dict:
    """Fetch account balance.

    Returns:
        dict with balance info or error
    """
    try:
        headers = get_auth_headers("GET", BALANCE_PATH)
        resp = requests.get(BASE_URL + BALANCE_PATH, headers=headers, timeout=10)

        if resp.status_code == 200:
            return {"success": True, "data": resp.json(), "error": None}
        else:
            return {
                "success": False,
                "data": None,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
            }
    except Exception as e:
        return {"success": False, "data": None, "error": str(e)}


def get_order_status(order_id: str) -> dict:
    """Get status of an order by ID.

    Returns:
        dict with order status or error
    """
    path = f"/trade-api/v2/portfolio/orders/{order_id}"
    try:
        headers = get_auth_headers("GET", path)
        resp = requests.get(BASE_URL + path, headers=headers, timeout=10)

        if resp.status_code == 200:
            return {"success": True, "data": resp.json(), "error": None}
        else:
            return {
                "success": False,
                "data": None,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
            }
    except Exception as e:
        return {"success": False, "data": None, "error": str(e)}


def get_open_orders() -> dict:
    """Fetch all open/resting orders.

    Returns:
        dict with keys: success, orders (list), total_cost_cents (int), error
    """
    try:
        headers = get_auth_headers("GET", ORDERS_PATH)
        resp = requests.get(
            BASE_URL + ORDERS_PATH,
            params={"status": "resting"},
            headers=headers,
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            orders = data.get("orders", [])
            # Sum up cost of all open orders: price * remaining_count
            total_cost_cents = 0
            for o in orders:
                price = o.get("yes_price", 0)
                remaining = o.get("remaining_count", 0)
                total_cost_cents += price * remaining
            return {
                "success": True,
                "orders": orders,
                "total_cost_cents": total_cost_cents,
                "error": None,
            }
        else:
            return {
                "success": False,
                "orders": [],
                "total_cost_cents": 0,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except Exception as e:
        return {"success": False, "orders": [], "total_cost_cents": 0, "error": str(e)}


def cancel_order(order_id: str, dry_run: bool = False) -> dict:
    """Cancel an order.

    Args:
        order_id: Order ID to cancel
        dry_run: If True, log but don't actually cancel

    Returns:
        dict with success flag and error message if any
    """
    if dry_run:
        print(f"[DRY RUN] Would cancel order {order_id}")
        return {"success": True, "error": None}

    path = f"/trade-api/v2/portfolio/orders/{order_id}"
    try:
        headers = get_auth_headers("DELETE", path)
        resp = requests.delete(BASE_URL + path, headers=headers, timeout=10)

        if resp.status_code in (200, 204):
            return {"success": True, "error": None}
        else:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
