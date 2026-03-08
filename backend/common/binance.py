"""Binance API utilities for fetching BTC prices."""

import requests

BINANCE_PRICE_URL = "https://api.binance.us/api/v3/ticker/price"
BINANCE_KLINES_URL = "https://api.binance.us/api/v3/klines"
SYMBOL = "BTCUSDT"


def get_binance_current_price():
    """Fetch live BTC/USDT spot price from Binance.

    Returns:
        (float, None) on success
        (None, str) on error
    """
    try:
        response = requests.get(BINANCE_PRICE_URL, params={"symbol": SYMBOL})
        response.raise_for_status()
        data = response.json()
        return float(data["price"]), None
    except Exception as e:
        return None, str(e)


def get_binance_open_price(target_time_utc):
    """Fetch 1-hour kline open price at target time.

    Args:
        target_time_utc: datetime object

    Returns:
        (float, None) on success
        (None, str) on error
    """
    try:
        timestamp_ms = int(target_time_utc.timestamp() * 1000)
        params = {
            "symbol": SYMBOL,
            "interval": "1h",
            "startTime": timestamp_ms,
            "limit": 1
        }
        response = requests.get(BINANCE_KLINES_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if not data:
            return None, "Candle not found yet"

        open_price = float(data[0][1])
        return open_price, None
    except Exception as e:
        return None, str(e)
