import time
import datetime
from polymarket.markets import fetch_polymarket_data_struct
from kalshi.markets import fetch_kalshi_data_struct
from arbitrage.engine import find_opportunities


def check_arbitrage():
    """Check for arbitrage opportunities and print results."""
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Scanning for arbitrage...")

    # Fetch Data
    poly_data, poly_err = fetch_polymarket_data_struct()
    kalshi_data, kalshi_err = fetch_kalshi_data_struct()

    if poly_err:
        print(f"Polymarket Error: {poly_err}")
        return
    if kalshi_err:
        print(f"Kalshi Error: {kalshi_err}")
        return

    if not poly_data or not kalshi_data:
        print("Missing data.")
        return

    # Polymarket Data
    poly_strike = poly_data.get("price_to_beat")

    if poly_strike is None:
        print("Polymarket Strike is None")
        return

    poly_up_cost = poly_data["prices"].get("Up", 0.0)
    poly_down_cost = poly_data["prices"].get("Down", 0.0)

    print(f"POLYMARKET | Strike: ${poly_strike:,.2f} | Up: ${poly_up_cost:.3f} | Down: ${poly_down_cost:.3f}")

    # Kalshi Data
    kalshi_markets = kalshi_data.get("markets", [])
    if not kalshi_markets:
        print("No Kalshi markets found")
        return

    # Find opportunities
    opportunities, _ = find_opportunities(poly_data, kalshi_data)

    # Print nearby Kalshi markets
    for km in kalshi_markets:
        kalshi_strike = km["strike"]
        kalshi_yes_cost = km["yes_ask"] / 100.0
        kalshi_no_cost = km["no_ask"] / 100.0

        if abs(kalshi_strike - poly_strike) < 2500:
            print(f"  KALSHI | Strike: ${kalshi_strike:,.2f} | Yes: ${kalshi_yes_cost:.2f} | No: ${kalshi_no_cost:.2f}")

    # Print opportunities
    if not opportunities:
        print("No risk-free arbitrage found.")
    else:
        for opp in opportunities:
            margin = opp["margin"]
            kalshi_strike = opp["kalshi_strike"]
            total_cost = opp["total_cost"]

            print(f"!!! ARBITRAGE FOUND !!!")
            print(f"Type: {opp['type']}")
            print(f"Strategy: Buy Poly {opp['poly_leg']} + Kalshi {opp['kalshi_leg']}")
            print(f"Total Cost: ${total_cost:.3f}")
            print(f"Min Payout: $1.00")
            print(f"Risk-Free Profit: ${margin:.3f} per unit")

    print("-" * 50)

def main():
    print("Starting Arbitrage Bot...")
    print("Press Ctrl+C to stop.")
    while True:
        try:
            check_arbitrage()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
