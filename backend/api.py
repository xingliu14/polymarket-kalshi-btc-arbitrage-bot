from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from polymarket.markets import fetch_polymarket_data_struct
from kalshi.markets import fetch_kalshi_data_struct
from kalshi.trader import get_open_orders as kalshi_get_open_orders, get_balance as kalshi_get_balance, get_market_positions as kalshi_get_market_positions
from polymarket.trader import get_open_orders as poly_get_open_orders, get_balance as poly_get_balance
from arbitrage.engine import find_opportunities
import datetime
import json
import os

TRADE_LOG_FILE = os.getenv("TRADE_LOG_FILE", "trade_history.json")

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/arbitrage")
def get_arbitrage_data():
    """Fetch arbitrage data from Polymarket and Kalshi."""
    # Fetch data
    poly_data, poly_err = fetch_polymarket_data_struct()
    kalshi_data, kalshi_err = fetch_kalshi_data_struct()

    response = {
        "timestamp": datetime.datetime.now().isoformat(),
        "polymarket": poly_data,
        "kalshi": kalshi_data,
        "checks": [],
        "opportunities": [],
        "errors": []
    }

    if poly_err:
        response["errors"].append(poly_err)
    if kalshi_err:
        response["errors"].append(kalshi_err)

    if not poly_data or not kalshi_data:
        return response

    # Find opportunities using arbitrage engine
    opportunities, checks = find_opportunities(poly_data, kalshi_data)

    response["opportunities"] = opportunities
    response["checks"] = checks

    return response

@app.get("/positions")
def get_positions():
    """Fetch open orders and balances from both platforms."""
    kalshi_orders_result = {"orders": [], "total_cost_cents": 0, "error": None}
    kalshi_positions_result = {"positions": [], "error": None}
    poly_orders_result = {"orders": [], "total_cost_usdc": 0.0, "error": None}
    kalshi_balance_cents = None
    poly_balance_usdc = None
    kalshi_balance_error = None
    poly_balance_error = None

    try:
        kalshi_orders_result = kalshi_get_open_orders()
    except Exception as e:
        kalshi_orders_result["error"] = str(e)

    try:
        kalshi_positions_result = kalshi_get_market_positions()
    except Exception as e:
        kalshi_positions_result["error"] = str(e)

    try:
        poly_orders_result = poly_get_open_orders()
    except Exception as e:
        poly_orders_result["error"] = str(e)

    try:
        kb = kalshi_get_balance()
        if kb["success"]:
            kalshi_balance_cents = kb["data"].get("balance", 0)
        else:
            kalshi_balance_error = kb.get("error")
    except Exception as e:
        kalshi_balance_error = str(e)

    try:
        pb = poly_get_balance()
        if pb["success"]:
            raw = pb["data"].get("balance", "0")
            poly_balance_usdc = int(raw) / 1_000_000
        else:
            poly_balance_error = pb.get("error")
    except Exception as e:
        poly_balance_error = str(e)

    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "kalshi": {
            "orders": kalshi_orders_result.get("orders", []),
            "positions": kalshi_positions_result.get("positions", []),
            "total_cost_usd": kalshi_orders_result.get("total_cost_cents", 0) / 100,
            "balance_usd": kalshi_balance_cents / 100 if kalshi_balance_cents is not None else None,
            "balance_error": kalshi_balance_error,
            "error": kalshi_orders_result.get("error"),
            "positions_error": kalshi_positions_result.get("error"),
        },
        "polymarket": {
            "orders": poly_orders_result.get("orders", []),
            "total_cost_usd": poly_orders_result.get("total_cost_usdc", 0.0),
            "balance_usd": poly_balance_usdc,
            "balance_error": poly_balance_error,
            "error": poly_orders_result.get("error"),
        },
    }


@app.get("/trades")
def get_trades():
    """Return trade history and P&L from the auto trader log."""
    trades = []
    if os.path.exists(TRADE_LOG_FILE):
        try:
            with open(TRADE_LOG_FILE, "r") as f:
                trades = json.load(f)
        except Exception:
            pass

    # Compute P&L summary
    total_pnl = 0.0
    wins = 0
    losses = 0
    for t in trades:
        status = t.get("status", "")
        opp = t.get("opportunity", {})
        margin = opp.get("margin", 0)
        if status in ("filled", "dry_run"):
            total_pnl += margin
            wins += 1
        elif status == "partial_kalshi_only":
            total_pnl -= opp.get("kalshi_cost", 0)
            losses += 1
        elif status == "partial_poly_only":
            total_pnl -= opp.get("poly_cost", 0)
            losses += 1

    # Return most recent first, capped at 50
    return {
        "trades": list(reversed(trades[-50:])),
        "pnl": {
            "total": total_pnl,
            "wins": wins,
            "losses": losses,
            "num_trades": wins + losses,
        },
    }


@app.get("/debug/kalshi-orders")
def debug_kalshi_orders():
    """Return raw Kalshi orders response for debugging (no status filter)."""
    from kalshi.auth import get_auth_headers
    import requests as req
    BASE_URL = "https://api.elections.kalshi.com"
    ORDERS_PATH = "/trade-api/v2/portfolio/orders"
    try:
        headers = get_auth_headers("GET", ORDERS_PATH)
        resp = req.get(BASE_URL + ORDERS_PATH, params={"limit": 50}, headers=headers, timeout=10)
        return {
            "status_code": resp.status_code,
            "raw": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
