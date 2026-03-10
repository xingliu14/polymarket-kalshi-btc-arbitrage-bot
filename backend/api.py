from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from polymarket.markets import fetch_polymarket_data_struct
from kalshi.markets import fetch_kalshi_data_struct
from kalshi.trader import get_open_orders as kalshi_get_open_orders, get_balance as kalshi_get_balance
from polymarket.trader import get_open_orders as poly_get_open_orders, get_balance as poly_get_balance
from arbitrage.engine import find_opportunities
import datetime

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
    kalshi_orders_result = kalshi_get_open_orders()
    poly_orders_result = poly_get_open_orders()
    kalshi_balance_result = kalshi_get_balance()
    poly_balance_result = poly_get_balance()

    kalshi_balance_cents = None
    if kalshi_balance_result["success"]:
        kalshi_balance_cents = kalshi_balance_result["data"].get("balance", 0)

    poly_balance_usdc = None
    if poly_balance_result["success"]:
        raw = poly_balance_result["data"].get("balance", "0")
        poly_balance_usdc = int(raw) / 1_000_000

    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "kalshi": {
            "orders": kalshi_orders_result.get("orders", []),
            "total_cost_usd": kalshi_orders_result.get("total_cost_cents", 0) / 100,
            "balance_usd": kalshi_balance_cents / 100 if kalshi_balance_cents is not None else None,
            "error": kalshi_orders_result.get("error"),
        },
        "polymarket": {
            "orders": poly_orders_result.get("orders", []),
            "total_cost_usd": poly_orders_result.get("total_cost_usdc", 0.0),
            "balance_usd": poly_balance_usdc,
            "error": poly_orders_result.get("error"),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
