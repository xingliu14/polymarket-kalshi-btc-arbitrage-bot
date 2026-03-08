"""Automated Kalshi arbitrage trading bot.

Detects arbitrage opportunities and automatically places Kalshi orders.

Configuration via environment variables:
- MIN_MARGIN: Minimum profit margin to trade (default 0.02 = 2%)
- CONTRACTS_PER_TRADE: Contracts to buy per trade (default 1)
- POLL_INTERVAL: Seconds between checks (default 5)
- DRY_RUN: If true, log orders instead of placing (default "True")
"""

import os
import time
import datetime
from polymarket.markets import fetch_polymarket_data_struct
from kalshi.markets import fetch_kalshi_data_struct
from kalshi.trader import place_order
from arbitrage.engine import find_opportunities

# Configuration
MIN_MARGIN = float(os.getenv("MIN_MARGIN", "0.02"))
CONTRACTS_PER_TRADE = int(os.getenv("CONTRACTS_PER_TRADE", "1"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
DRY_RUN = os.getenv("DRY_RUN", "True").lower() in ("true", "1", "yes")

print(f"Auto Trader Config:")
print(f"  MIN_MARGIN: {MIN_MARGIN}")
print(f"  CONTRACTS_PER_TRADE: {CONTRACTS_PER_TRADE}")
print(f"  POLL_INTERVAL: {POLL_INTERVAL}s")
print(f"  DRY_RUN: {DRY_RUN}")
print()


def run_arbitrage_check():
    """Run a single arbitrage detection cycle.

    Returns:
        dict with opportunities and execution results
    """
    result = {
        "timestamp": datetime.datetime.now().isoformat(),
        "opportunities": [],
        "executed_trades": [],
        "errors": []
    }

    # Fetch data
    poly_data, poly_err = fetch_polymarket_data_struct()
    kalshi_data, kalshi_err = fetch_kalshi_data_struct()

    if poly_err:
        result["errors"].append(f"Polymarket error: {poly_err}")
    if kalshi_err:
        result["errors"].append(f"Kalshi error: {kalshi_err}")

    if not poly_data or not kalshi_data:
        return result

    # Find opportunities using arbitrage engine
    opportunities, _ = find_opportunities(poly_data, kalshi_data)

    result["opportunities"] = opportunities

    # Execute trades for opportunities meeting margin threshold
    for opp in opportunities:
        if opp["margin"] >= MIN_MARGIN:
            execution = execute_trade(opp, opp["kalshi_market"])
            result["executed_trades"].append(execution)

    return result


def execute_trade(opportunity: dict, kalshi_market: dict) -> dict:
    """
    Execute a trade based on an opportunity.

    Places a Kalshi order (or simulates placement in dry-run mode).

    Returns:
        dict with execution details
    """
    kalshi_leg = opportunity["kalshi_leg"]
    side = "yes" if kalshi_leg == "Yes" else "no"
    price_cents = kalshi_market["yes_ask"] if side == "yes" else kalshi_market["no_ask"]

    # Convert to reasonable order price
    # If buying Yes at ask price, place at ask (or slightly below for limit)
    # For safety, use the ask as displayed (already in cents)
    order_price = int(max(1, min(99, price_cents)))

    execution = {
        "timestamp": datetime.datetime.now().isoformat(),
        "opportunity": opportunity,
        "order_details": {
            "ticker": kalshi_market["ticker"],
            "side": side,
            "action": "buy",
            "count": CONTRACTS_PER_TRADE,
            "yes_price_cents": order_price,
        },
        "order_result": None,
    }

    # Place order
    result = place_order(
        ticker=kalshi_market["ticker"],
        side=side,
        action="buy",
        count=CONTRACTS_PER_TRADE,
        yes_price_cents=order_price,
        dry_run=DRY_RUN
    )

    execution["order_result"] = result
    execution["status"] = "success" if result["success"] else "failed"

    return execution


def main():
    """Main trading loop."""
    print(f"Starting automated arbitrage trading at {datetime.datetime.now()}")
    print()

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            print(f"--- Cycle {cycle_count} at {datetime.datetime.now().isoformat()} ---")

            result = run_arbitrage_check()

            # Report results
            if result["errors"]:
                print(f"Errors: {result['errors']}")

            if result["opportunities"]:
                print(f"Found {len(result['opportunities'])} arbitrage opportunities:")
                for opp in result["opportunities"]:
                    print(
                        f"  {opp['type']}: "
                        f"strike=${opp['kalshi_strike']}, "
                        f"margin={opp['margin']:.4f} "
                        f"(cost ${opp['total_cost']:.2f})"
                    )
            else:
                print("No arbitrage opportunities found")

            if result["executed_trades"]:
                print(f"Executed {len(result['executed_trades'])} trades:")
                for trade in result["executed_trades"]:
                    status = trade["status"]
                    order = trade["order_result"]
                    msg = f"  [{status}] {trade['order_details']['side'].upper()} "
                    if status == "success":
                        msg += f"Order {order['order_id'][:8]}..."
                    else:
                        msg += f"Error: {order['error']}"
                    print(msg)

            print()
            print(f"Sleeping for {POLL_INTERVAL} seconds...")
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nShutdown requested. Exiting.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
