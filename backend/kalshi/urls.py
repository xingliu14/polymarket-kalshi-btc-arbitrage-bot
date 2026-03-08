"""Kalshi URL generation utilities."""

import datetime
import pytz

BASE_URL = "https://kalshi.com/markets/kxbtcd/bitcoin-price-abovebelow/"


def generate_kalshi_slug(target_time):
    """Generate Kalshi event slug for a given datetime.

    Format: kxbtcd-[YY][MMM][DD][HH]
    Example: kxbtcd-25nov2614 (Nov 26, 2025, 14:00 ET)
    """
    et_tz = pytz.timezone("US/Eastern")
    if target_time.tzinfo is None:
        target_time = pytz.utc.localize(target_time).astimezone(et_tz)
    else:
        target_time = target_time.astimezone(et_tz)

    year = target_time.strftime("%y")
    month = target_time.strftime("%b").lower()
    day = target_time.strftime("%d")
    hour = target_time.strftime("%H")

    slug = f"kxbtcd-{year}{month}{day}{hour}"
    return slug


def generate_kalshi_url(target_time):
    """Generate full Kalshi URL for a given datetime."""
    slug = generate_kalshi_slug(target_time)
    return f"{BASE_URL}{slug}"
