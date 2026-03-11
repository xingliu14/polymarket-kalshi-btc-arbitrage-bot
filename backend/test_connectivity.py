"""Phase 3 & 6: Remote connectivity tests and dry-run auto trader.

Run from backend/: python test_connectivity.py
"""

import os
import sys
import json
import traceback

# Load .env from project root
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"

results = []


def test(name, fn):
    """Run a test and record result."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    try:
        fn()
        results.append((name, True, None))
        print(f"  [{PASS}] {name}")
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"  [{FAIL}] {name}: {e}")
        traceback.print_exc()


# ─── Phase 3: Read-Only API Connectivity ───────────────────────────────────

def test_binance_price():
    from common.binance import get_binance_current_price
    price, err = get_binance_current_price()
    assert err is None, f"Binance error: {err}"
    assert price is not None and price > 0, f"Invalid price: {price}"
    print(f"  BTC/USDT: ${price:,.2f}")


def test_polymarket_markets():
    from polymarket.markets import fetch_polymarket_data_struct
    data, err = fetch_polymarket_data_struct()
    assert err is None, f"Polymarket error: {err}"
    assert data is not None, "No data returned"
    print(f"  Slug: {data['slug']}")
    print(f"  Target time: {data['target_time_utc']}")
    print(f"  Price to beat: {data.get('price_to_beat')}")
    print(f"  Prices: {data['prices']}")
    print(f"  Token IDs: { {k: v[:16]+'...' for k, v in data['token_ids'].items()} }")
    assert len(data['prices']) > 0, "No prices found"


def test_kalshi_markets():
    from kalshi.markets import fetch_kalshi_data_struct
    data, err = fetch_kalshi_data_struct()
    assert err is None, f"Kalshi error: {err}"
    assert data is not None, "No data returned"
    markets = data.get("markets", [])
    print(f"  Event ticker: {data['event_ticker']}")
    print(f"  Current price: ${data['current_price']:,.2f}" if data['current_price'] else "  Current price: N/A")
    print(f"  Markets found: {len(markets)}")
    if markets:
        for m in markets[:3]:
            print(f"    Strike ${m['strike']:,.0f}: YES ask={m['yes_ask']}c, NO ask={m['no_ask']}c")
    assert len(markets) > 0, "No Kalshi markets found"


def test_kalshi_balance():
    from kalshi.trader import get_balance
    result = get_balance()
    if result["success"]:
        balance_cents = result["data"].get("balance", 0)
        print(f"  Kalshi balance: {balance_cents}c (${balance_cents/100:.2f})")
    else:
        raise AssertionError(f"Kalshi balance failed: {result['error']}")


def test_polymarket_balance():
    from polymarket.trader import get_balance
    result = get_balance()
    if result["success"]:
        raw = result["data"].get("balance", "0")
        usdc = int(raw) / 1_000_000
        source = result["data"].get("source", "sdk")
        print(f"  Poly balance: {raw} raw = ${usdc:.2f} USDC (source: {source})")
    else:
        raise AssertionError(f"Poly balance failed: {result['error']}")


# ─── Phase 3.5: Arbitrage Engine (read-only) ──────────────────────────────

def test_arbitrage_scan():
    from polymarket.markets import fetch_polymarket_data_struct
    from kalshi.markets import fetch_kalshi_data_struct
    from arbitrage.engine import find_opportunities

    poly_data, poly_err = fetch_polymarket_data_struct()
    kalshi_data, kalshi_err = fetch_kalshi_data_struct()

    assert poly_err is None, f"Polymarket: {poly_err}"
    assert kalshi_err is None, f"Kalshi: {kalshi_err}"

    opportunities, checks = find_opportunities(poly_data, kalshi_data)
    print(f"  Checks performed: {len(checks)}")
    print(f"  Opportunities found: {len(opportunities)}")
    for opp in opportunities:
        print(f"    {opp['type']}: strike=${opp['kalshi_strike']:,.0f}, "
              f"margin={opp['margin']:.4f}, cost=${opp['total_cost']:.4f}")


# ─── Phase 6: Dry-Run Auto Trader (single cycle) ──────────────────────────

def test_dry_run_single_cycle():
    # Force dry run
    os.environ["DRY_RUN"] = "True"
    os.environ["MIN_MARGIN"] = "0.01"  # Lower threshold to catch more opportunities
    os.environ["POLL_INTERVAL"] = "5"

    from auto_trader import run_arbitrage_check, DRY_RUN
    print(f"  DRY_RUN confirmed: {DRY_RUN}")
    assert DRY_RUN, "DRY_RUN must be True for this test!"

    result = run_arbitrage_check()
    print(f"  Timestamp: {result['timestamp']}")
    print(f"  Errors: {result['errors']}")
    print(f"  Opportunities: {len(result['opportunities'])}")
    print(f"  Executed trades (dry run): {len(result['executed_trades'])}")

    for trade in result["executed_trades"]:
        print(f"    Status: {trade['status']}")
        if trade.get("kalshi_order"):
            print(f"    Kalshi order: {trade['kalshi_order']}")
        if trade.get("poly_order"):
            print(f"    Poly order: {trade['poly_order']}")

    # Even if no opportunities, that's OK — the bot ran without crashing
    print(f"  Single cycle completed successfully")


# ─── Run all tests ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PHASE 3: Read-Only API Connectivity Tests")
    print("=" * 60)

    test("1. Binance BTC Price", test_binance_price)
    test("2. Polymarket Markets (CLOB)", test_polymarket_markets)
    test("3. Kalshi Markets", test_kalshi_markets)
    test("4. Kalshi Balance (auth required)", test_kalshi_balance)
    test("5. Polymarket Balance (auth required)", test_polymarket_balance)
    test("6. Arbitrage Engine Scan", test_arbitrage_scan)

    print("\n" + "=" * 60)
    print("PHASE 6: Dry-Run Auto Trader (single cycle)")
    print("=" * 60)

    test("7. Auto Trader Dry Run", test_dry_run_single_cycle)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, err in results:
        status = PASS if ok else FAIL
        suffix = f" — {err}" if err else ""
        print(f"  [{status}] {name}{suffix}")
    print(f"\n  {passed} passed, {failed} failed out of {len(results)} tests")

    sys.exit(1 if failed > 0 else 0)
