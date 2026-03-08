"""Polymarket URL generation utilities."""

import datetime
import pytz

BASE_URL = "https://polymarket.com/event/"


def generate_slug(target_time):
    """Generate Polymarket event slug for a given datetime.

    Format: bitcoin-up-or-down-[month]-[day]-[hour][am/pm]-et
    Example: bitcoin-up-or-down-november-26-1pm-et
    """
    et_tz = pytz.timezone("US/Eastern")
    if target_time.tzinfo is None:
        target_time = pytz.utc.localize(target_time).astimezone(et_tz)
    else:
        target_time = target_time.astimezone(et_tz)

    month = target_time.strftime("%B").lower()
    day = target_time.day
    hour_int = int(target_time.strftime("%I"))
    am_pm = target_time.strftime("%p").lower()

    slug = f"bitcoin-up-or-down-{month}-{day}-{hour_int}{am_pm}-et"
    return slug


def generate_market_url(target_time):
    """Generate full Polymarket URL for a given datetime."""
    slug = generate_slug(target_time)
    return f"{BASE_URL}{slug}"


def get_next_market_urls(num_hours=5):
    """Generate URLs for the next num_hours hourly markets."""
    urls = []
    now = datetime.datetime.now(pytz.utc)
    next_hour = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)

    for i in range(num_hours):
        target_time = next_hour + datetime.timedelta(hours=i)
        urls.append(generate_market_url(target_time))

    return urls
