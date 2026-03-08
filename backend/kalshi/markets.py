"""Kalshi market data fetching."""

import requests
import datetime
import pytz
import re
from common.binance import get_binance_current_price
from common.market_time import get_current_market_urls

KALSHI_API_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"


def get_kalshi_markets(event_ticker):
    """Fetch Kalshi markets for a given event ticker.

    Args:
        event_ticker: Event ticker string (e.g., 'KXBTCD-250307-14')

    Returns:
        (list, None) on success
        (None, str) on error
    """
    try:
        params = {"limit": 100, "event_ticker": event_ticker}
        response = requests.get(KALSHI_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("markets", []), None
    except Exception as e:
        return None, str(e)


def parse_strike(subtitle):
    """Parse strike price from market subtitle string.

    Format: "$96,250 or above" or "$97,000 at or above"

    Returns:
        float strike price or 0.0 if parse fails
    """
    match = re.search(r"\$([\d,]+)", subtitle)
    if match:
        return float(match.group(1).replace(",", ""))
    return 0.0


def fetch_kalshi_data_struct():
    """Fetch and structure Kalshi market data.

    Returns:
        (dict, None) on success with keys: event_ticker, current_price, markets
        (None, str) on error
    """
    try:
        market_info = get_current_market_urls()
        kalshi_url = market_info["kalshi"]

        # Extract event ticker from URL
        event_ticker = kalshi_url.split("/")[-1].upper()

        # Fetch current BTC price
        current_price, _ = get_binance_current_price()

        # Fetch Kalshi markets
        markets, err = get_kalshi_markets(event_ticker)
        if err:
            return None, f"Kalshi Error: {err}"

        if not markets:
            return [], None

        # Parse strikes and structure market data
        market_data = []
        for m in markets:
            strike = parse_strike(m.get("subtitle", ""))
            if strike > 0:
                market_data.append({
                    "ticker": m.get("ticker"),  # BUG FIX: Include ticker field
                    "strike": strike,
                    "yes_bid": m.get("yes_bid", 0),
                    "yes_ask": m.get("yes_ask", 0),
                    "no_bid": m.get("no_bid", 0),
                    "no_ask": m.get("no_ask", 0),
                    "subtitle": m.get("subtitle")
                })

        # Sort by strike price
        market_data.sort(key=lambda x: x["strike"])

        return {
            "event_ticker": event_ticker,
            "current_price": current_price,
            "markets": market_data
        }, None

    except Exception as e:
        return None, str(e)


def main():
    """CLI entry point."""
    data, err = fetch_kalshi_data_struct()

    if err:
        print(f"Error: {err}")
        return

    print(f"Fetching data for Event: {data['event_ticker']}")
    if data["current_price"]:
        print(f"CURRENT PRICE: ${data['current_price']:,.2f}")

    market_data = data["markets"]
    if not market_data:
        print("No markets found.")
        return

    # Find the market closest to current price for display
    current_price = data["current_price"] or 0
    closest_idx = 0
    min_diff = float("inf")

    for i, m in enumerate(market_data):
        diff = abs(m["strike"] - current_price)
        if diff < min_diff:
            min_diff = diff
            closest_idx = i

    # Select 3 markets
    start_idx = max(0, closest_idx - 1)
    end_idx = min(len(market_data), start_idx + 3)

    if end_idx - start_idx < 3 and start_idx > 0:
        start_idx = max(0, end_idx - 3)

    selected_markets = market_data[start_idx:end_idx]

    # Print Data
    print("-" * 30)
    for i, m in enumerate(selected_markets):
        print(f"PRICE TO BEAT {i+1}: {m['subtitle']}")
        print(f"BUY YES PRICE {i+1}: {m['yes_ask']}c, BUY NO PRICE {i+1}: {m['no_ask']}c")
        print()


if __name__ == "__main__":
    main()
