"""Kalshi WebSocket subscriber for real-time market data.

Usage:
    import asyncio
    from kalshi.ws import subscribe_orderbook

    async def on_message(msg):
        print(msg)

    asyncio.run(subscribe_orderbook("KXBTCD-250326-14", on_message))
"""

import asyncio
import websockets
import json
from kalshi.auth import get_auth_headers

WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
WS_PATH = "/trade-api/ws/v2"


async def subscribe_orderbook(ticker: str, on_message_callback, dry_run: bool = False):
    """Subscribe to orderbook delta updates for a market.

    Args:
        ticker: Market ticker (e.g., "KXBTCD-250326-14")
        on_message_callback: async callable that receives message dict
        dry_run: If True, don't actually connect, just return
    """
    if dry_run:
        print(f"[DRY RUN] Would subscribe to orderbook for {ticker}")
        return

    headers = get_auth_headers("GET", WS_PATH)

    try:
        async with websockets.connect(WS_URL, additional_headers=headers) as ws:
            # Send subscription request
            subscribe_msg = {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_ticker": ticker
                }
            }
            await ws.send(json.dumps(subscribe_msg))
            print(f"Subscribed to {ticker} orderbook updates")

            # Listen for messages
            async for raw_msg in ws:
                try:
                    msg = json.loads(raw_msg)
                    await on_message_callback(msg)
                except json.JSONDecodeError:
                    print(f"Failed to parse WebSocket message: {raw_msg}")
    except asyncio.CancelledError:
        print(f"WebSocket subscription for {ticker} cancelled")
    except Exception as e:
        print(f"WebSocket error for {ticker}: {e}")


async def subscribe_multiple(tickers: list, on_message_callback, dry_run: bool = False):
    """Subscribe to multiple markets in parallel.

    Args:
        tickers: List of market tickers
        on_message_callback: async callable that receives message dict
        dry_run: If True, don't actually connect
    """
    tasks = [subscribe_orderbook(t, on_message_callback, dry_run=dry_run) for t in tickers]
    await asyncio.gather(*tasks)
