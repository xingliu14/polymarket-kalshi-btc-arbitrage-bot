"""Polymarket market data fetching."""

import requests
import json
import datetime
import pytz
from common.binance import get_binance_current_price, get_binance_open_price
from common.market_time import get_current_market_urls

POLYMARKET_API_URL = "https://gamma-api.polymarket.com/events"
CLOB_API_URL = "https://clob.polymarket.com/book"


def get_clob_price(token_id):
    """Fetch best ask price from CLOB for a token.

    Args:
        token_id: Token ID string

    Returns:
        float ask price or None on error
    """
    try:
        response = requests.get(CLOB_API_URL, params={"token_id": token_id})
        response.raise_for_status()
        data = response.json()

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        best_ask = 0.0

        if asks:
            # Asks: We want the LOWEST price someone is willing to sell for
            best_ask = min(float(a["price"]) for a in asks)

        return best_ask if best_ask > 0 else 0.0
    except Exception as e:
        return None


def get_polymarket_data(slug):
    """Fetch Polymarket event data by slug.

    Args:
        slug: Event slug string

    Returns:
        (dict, None) with prices on success
        (None, str) on error
    """
    try:
        response = requests.get(POLYMARKET_API_URL, params={"slug": slug})
        response.raise_for_status()
        data = response.json()

        if not data:
            return None, "Event not found"

        event = data[0]
        markets = event.get("markets", [])
        if not markets:
            return None, "Markets not found in event"

        market = markets[0]

        # BUG FIX: Replace eval() with json.loads() for security
        clob_token_ids = json.loads(market.get("clobTokenIds", "[]"))
        outcomes = json.loads(market.get("outcomes", "[]"))

        if len(clob_token_ids) != 2:
            return None, "Unexpected number of tokens"

        # Fetch prices for each token
        prices = {}
        for outcome, token_id in zip(outcomes, clob_token_ids):
            price = get_clob_price(token_id)
            if price is not None:
                prices[outcome] = price
            else:
                prices[outcome] = 0.0

        return prices, None
    except Exception as e:
        return None, str(e)


def fetch_polymarket_data_struct():
    """Fetch and structure Polymarket data.

    Returns:
        (dict, None) on success with keys: price_to_beat, current_price, prices, slug, target_time_utc
        (None, str) on error
    """
    try:
        market_info = get_current_market_urls()
        polymarket_url = market_info["polymarket"]
        target_time_utc = market_info["target_time_utc"]

        # Extract slug from URL
        slug = polymarket_url.split("/")[-1]

        # Fetch data
        poly_prices, poly_err = get_polymarket_data(slug)
        current_price, _ = get_binance_current_price()
        price_to_beat, _ = get_binance_open_price(target_time_utc)

        if poly_err:
            return None, f"Polymarket Error: {poly_err}"

        return {
            "price_to_beat": price_to_beat,
            "current_price": current_price,
            "prices": poly_prices,
            "slug": slug,
            "target_time_utc": target_time_utc
        }, None

    except Exception as e:
        return None, str(e)


def main():
    """CLI entry point."""
    data, err = fetch_polymarket_data_struct()

    if err:
        print(f"Error: {err}")
        return

    print(f"Fetching data for: {data['slug']}")
    print(f"Target Time (UTC): {data['target_time_utc']}")
    print("-" * 50)

    if data["price_to_beat"] is None:
        print("PRICE TO BEAT: Error")
    else:
        print(f"PRICE TO BEAT: ${data['price_to_beat']:,.2f}")

    if data["current_price"] is None:
        print("CURRENT PRICE: Error")
    else:
        print(f"CURRENT PRICE: ${data['current_price']:,.2f}")

    up_price = data["prices"].get("Up", 0)
    down_price = data["prices"].get("Down", 0)
    print(f"BUY: UP ${up_price:.3f} & DOWN ${down_price:.3f}")


if __name__ == "__main__":
    main()
