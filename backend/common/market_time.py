"""Get current market times and URLs for both exchanges."""

import datetime
import pytz
from polymarket.urls import generate_market_url as generate_polymarket_url
from kalshi.urls import generate_kalshi_url


def get_current_market_urls():
    """Get the current active market URLs for Polymarket and Kalshi.

    'Current' is defined as the market expiring/resolving at the top of the next hour.

    Returns:
        dict with keys: polymarket, kalshi, target_time_utc, target_time_et
    """
    now = datetime.datetime.now(pytz.utc)

    # Target time is the current full hour
    target_time = now.replace(minute=0, second=0, microsecond=0)

    polymarket_url = generate_polymarket_url(target_time)

    # Kalshi uses the *next* hour for the current market identifier
    kalshi_target_time = target_time + datetime.timedelta(hours=1)
    kalshi_url = generate_kalshi_url(kalshi_target_time)

    return {
        "polymarket": polymarket_url,
        "kalshi": kalshi_url,
        "target_time_utc": target_time,
        "target_time_et": target_time.astimezone(pytz.timezone("US/Eastern"))
    }


if __name__ == "__main__":
    urls = get_current_market_urls()

    print(f"Current Time (UTC): {datetime.datetime.now(pytz.utc)}")
    print(f"Target Market Time (ET): {urls['target_time_et']}")
    print("-" * 50)
    print(f"Polymarket: {urls['polymarket']}")
    print(f"Kalshi:     {urls['kalshi']}")
