"""Automated dual-leg arbitrage trading bot.

Detects arbitrage opportunities between Polymarket and Kalshi, then
executes both legs simultaneously with rollback on partial failure.

Configuration via environment variables:
- MIN_MARGIN: Minimum profit margin to trade (default 0.02 = 2%)
- MAX_TOTAL_COST: Max combined cost before rejecting for slippage (default 0.98)
- CONTRACTS_PER_TRADE: Contracts to buy per trade (default 1)
- POLY_SIZE_PER_TRADE: Polymarket shares per trade (default 1.0)
- POLL_INTERVAL: Seconds between checks (default 5)
- DRY_RUN: If true, log orders instead of placing (default "True")
- TRADE_LOG_FILE: Path to JSON trade log (default "trade_history.json")
- FILL_CHECK_ATTEMPTS: Number of times to poll for fill status (default 3)
- FILL_CHECK_DELAY: Seconds between fill status polls (default 2)
"""

import os
import sys
import time
import json
import datetime

from polymarket.markets import fetch_polymarket_data_struct
from kalshi.markets import fetch_kalshi_data_struct
from kalshi.trader import (
    place_order as kalshi_place_order,
    get_balance as kalshi_get_balance,
    get_order_status as kalshi_get_order_status,
    cancel_order as kalshi_cancel_order,
)
from polymarket.trader import (
    place_order as poly_place_order,
    get_balance as poly_get_balance,
    get_order_status as poly_get_order_status,
    cancel_order as poly_cancel_order,
)
from arbitrage.engine import find_opportunities

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MIN_MARGIN = float(os.getenv("MIN_MARGIN", "0.02"))
MAX_TOTAL_COST = float(os.getenv("MAX_TOTAL_COST", "0.98"))
CONTRACTS_PER_TRADE = int(os.getenv("CONTRACTS_PER_TRADE", "1"))
POLY_SIZE_PER_TRADE = float(os.getenv("POLY_SIZE_PER_TRADE", "1.0"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
DRY_RUN = os.getenv("DRY_RUN", "True").lower() in ("true", "1", "yes")
TRADE_LOG_FILE = os.getenv("TRADE_LOG_FILE", "trade_history.json")
FILL_CHECK_ATTEMPTS = int(os.getenv("FILL_CHECK_ATTEMPTS", "3"))
FILL_CHECK_DELAY = float(os.getenv("FILL_CHECK_DELAY", "2"))

print("Auto Trader Config:")
print(f"  MIN_MARGIN:       {MIN_MARGIN}")
print(f"  MAX_TOTAL_COST:   {MAX_TOTAL_COST}")
print(f"  CONTRACTS:        {CONTRACTS_PER_TRADE} (Kalshi) / {POLY_SIZE_PER_TRADE} (Poly)")
print(f"  POLL_INTERVAL:    {POLL_INTERVAL}s")
print(f"  DRY_RUN:          {DRY_RUN}")
print(f"  FILL_CHECKS:      {FILL_CHECK_ATTEMPTS}x @ {FILL_CHECK_DELAY}s")
print()


# ---------------------------------------------------------------------------
# Trade history logging
# ---------------------------------------------------------------------------
def _log_trade(record: dict):
    """Append a trade record to the JSON log file."""
    try:
        if os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, "r") as f:
                history = json.load(f)
        else:
            history = []
        history.append(record)
        with open(TRADE_LOG_FILE, "w") as f:
            json.dump(history, f, indent=2, default=str)
    except Exception as e:
        print(f"[WARN] Failed to write trade log: {e}")


# ---------------------------------------------------------------------------
# Balance pre-checks
# ---------------------------------------------------------------------------
def check_balances() -> dict:
    """Check balances on both platforms.

    Returns:
        dict with kalshi_balance_cents, poly_balance_usdc, errors
    """
    result = {
        "kalshi_balance_cents": None,
        "poly_balance_usdc": None,
        "errors": [],
    }

    # Kalshi balance
    kb = kalshi_get_balance()
    if kb["success"]:
        # Kalshi returns balance in cents
        result["kalshi_balance_cents"] = kb["data"].get("balance", 0)
    else:
        result["errors"].append(f"Kalshi balance error: {kb['error']}")

    # Polymarket balance
    pb = poly_get_balance()
    if pb["success"]:
        raw = pb["data"].get("balance", "0")
        # USDC has 6 decimals on Polygon
        result["poly_balance_usdc"] = int(raw) / 1_000_000
    else:
        result["errors"].append(f"Poly balance error: {pb['error']}")

    return result


def _has_sufficient_funds(balances: dict, opp: dict) -> tuple[bool, str]:
    """Check if we have enough funds for both legs.

    Args:
        balances: Output of check_balances()
        opp: Opportunity dict from engine

    Returns:
        (ok, reason)
    """
    # Kalshi: cost = price_cents * contracts (in cents)
    kalshi_cost_cents = int(opp["kalshi_cost"] * 100) * CONTRACTS_PER_TRADE
    if balances["kalshi_balance_cents"] is not None:
        if balances["kalshi_balance_cents"] < kalshi_cost_cents:
            return False, (
                f"Kalshi balance {balances['kalshi_balance_cents']}c "
                f"< required {kalshi_cost_cents}c"
            )

    # Polymarket: cost = price * size (in USDC)
    poly_cost_usdc = opp["poly_cost"] * POLY_SIZE_PER_TRADE
    if balances["poly_balance_usdc"] is not None:
        if balances["poly_balance_usdc"] < poly_cost_usdc:
            return False, (
                f"Poly balance ${balances['poly_balance_usdc']:.2f} "
                f"< required ${poly_cost_usdc:.2f}"
            )

    return True, ""


# ---------------------------------------------------------------------------
# Fill verification
# ---------------------------------------------------------------------------
def _check_kalshi_fill(order_id: str) -> dict:
    """Poll Kalshi for order fill status.

    Returns:
        dict with filled (bool), status (str), fill_price, error
    """
    for attempt in range(FILL_CHECK_ATTEMPTS):
        result = kalshi_get_order_status(order_id)
        if not result["success"]:
            return {"filled": False, "status": "unknown", "error": result["error"]}

        order = result["data"].get("order", result["data"])
        status = order.get("status", "")

        if status == "executed":
            return {
                "filled": True,
                "status": status,
                "fill_price": order.get("yes_price", order.get("no_price")),
                "error": None,
            }
        elif status in ("canceled", "expired"):
            return {"filled": False, "status": status, "error": None}

        # Still resting / pending — wait and retry
        if attempt < FILL_CHECK_ATTEMPTS - 1:
            time.sleep(FILL_CHECK_DELAY)

    return {"filled": False, "status": "pending", "error": "Timed out waiting for fill"}


def _check_poly_fill(order_id: str) -> dict:
    """Poll Polymarket for order fill status.

    Returns:
        dict with filled (bool), status (str), error
    """
    for attempt in range(FILL_CHECK_ATTEMPTS):
        result = poly_get_order_status(order_id)
        if not result["success"]:
            return {"filled": False, "status": "unknown", "error": result["error"]}

        order = result["data"]
        # Polymarket statuses: "live", "matched", "delayed", "canceled"
        size_matched = float(order.get("size_matched", "0"))
        original_size = float(order.get("original_size", "0"))

        if size_matched > 0 and size_matched >= original_size:
            return {"filled": True, "status": "matched", "error": None}
        elif order.get("status") == "canceled":
            return {"filled": False, "status": "canceled", "error": None}

        if attempt < FILL_CHECK_ATTEMPTS - 1:
            time.sleep(FILL_CHECK_DELAY)

    return {"filled": False, "status": "pending", "error": "Timed out waiting for fill"}


# ---------------------------------------------------------------------------
# Dual-leg trade execution
# ---------------------------------------------------------------------------
def execute_trade(opportunity: dict) -> dict:
    """Execute both legs of an arbitrage trade with rollback on failure.

    Places Kalshi and Polymarket orders. If one leg fails, cancels the other.

    Returns:
        dict with execution details for both legs
    """
    kalshi_market = opportunity["kalshi_market"]
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    execution = {
        "timestamp": timestamp,
        "opportunity": {
            "type": opportunity["type"],
            "kalshi_strike": opportunity["kalshi_strike"],
            "poly_leg": opportunity["poly_leg"],
            "kalshi_leg": opportunity["kalshi_leg"],
            "poly_cost": opportunity["poly_cost"],
            "kalshi_cost": opportunity["kalshi_cost"],
            "total_cost": opportunity["total_cost"],
            "margin": opportunity["margin"],
        },
        "kalshi_order": None,
        "poly_order": None,
        "kalshi_fill": None,
        "poly_fill": None,
        "status": "pending",
    }

    # --- Slippage check ---
    if opportunity["total_cost"] > MAX_TOTAL_COST:
        execution["status"] = "rejected_slippage"
        msg = (
            f"Total cost ${opportunity['total_cost']:.4f} "
            f"> max ${MAX_TOTAL_COST:.4f}"
        )
        execution["error"] = msg
        print(f"  [SKIP] Slippage: {msg}")
        _log_trade(execution)
        return execution

    # --- Prepare Kalshi order ---
    kalshi_side = "yes" if opportunity["kalshi_leg"] == "Yes" else "no"
    kalshi_price_cents = (
        kalshi_market["yes_ask"] if kalshi_side == "yes"
        else kalshi_market["no_ask"]
    )
    kalshi_price_cents = int(max(1, min(99, kalshi_price_cents)))

    # --- Prepare Polymarket order ---
    poly_token_id = opportunity.get("poly_token_id")
    poly_price = opportunity["poly_cost"]

    if not poly_token_id:
        execution["status"] = "failed"
        execution["error"] = "Missing Polymarket token_id for order placement"
        print(f"  [FAIL] {execution['error']}")
        _log_trade(execution)
        return execution

    # --- Place Kalshi order (leg 1) ---
    print(f"  Placing Kalshi {kalshi_side.upper()} @ {kalshi_price_cents}c ...")
    kalshi_result = kalshi_place_order(
        ticker=kalshi_market["ticker"],
        side=kalshi_side,
        action="buy",
        count=CONTRACTS_PER_TRADE,
        yes_price_cents=kalshi_price_cents,
        dry_run=DRY_RUN,
    )
    execution["kalshi_order"] = kalshi_result

    if not kalshi_result["success"]:
        execution["status"] = "failed_kalshi"
        execution["error"] = f"Kalshi order failed: {kalshi_result['error']}"
        print(f"  [FAIL] Kalshi: {kalshi_result['error']}")
        _log_trade(execution)
        return execution

    print(f"  Kalshi order placed: {kalshi_result['order_id']}")

    # --- Place Polymarket order (leg 2) ---
    print(f"  Placing Poly BUY {opportunity['poly_leg']} @ {poly_price:.4f} ...")
    poly_result = poly_place_order(
        token_id=poly_token_id,
        side="BUY",
        price=poly_price,
        size=POLY_SIZE_PER_TRADE,
        dry_run=DRY_RUN,
    )
    execution["poly_order"] = poly_result

    if not poly_result["success"]:
        # --- Rollback: cancel Kalshi order ---
        execution["status"] = "failed_poly_rollback"
        execution["error"] = f"Poly order failed: {poly_result['error']}"
        print(f"  [FAIL] Poly: {poly_result['error']}")
        print(f"  [ROLLBACK] Cancelling Kalshi order {kalshi_result['order_id']}...")

        cancel_result = kalshi_cancel_order(
            kalshi_result["order_id"], dry_run=DRY_RUN
        )
        execution["kalshi_cancel"] = cancel_result
        if cancel_result["success"]:
            print("  [ROLLBACK] Kalshi order cancelled")
        else:
            print(f"  [ROLLBACK WARN] Cancel failed: {cancel_result['error']}")

        _log_trade(execution)
        return execution

    print(f"  Poly order placed: {poly_result['order_id']}")

    # --- Verify fills ---
    if not DRY_RUN:
        print("  Checking fill status...")
        kalshi_fill = _check_kalshi_fill(kalshi_result["order_id"])
        poly_fill = _check_poly_fill(poly_result["order_id"])
        execution["kalshi_fill"] = kalshi_fill
        execution["poly_fill"] = poly_fill

        both_filled = kalshi_fill["filled"] and poly_fill["filled"]
        kalshi_unfilled = not kalshi_fill["filled"]
        poly_unfilled = not poly_fill["filled"]

        if both_filled:
            execution["status"] = "filled"
            print("  [OK] Both legs filled!")
        elif kalshi_unfilled and poly_unfilled:
            # Neither filled — cancel both
            execution["status"] = "unfilled_both"
            print("  [WARN] Neither leg filled, cancelling both...")
            kalshi_cancel_order(kalshi_result["order_id"])
            poly_cancel_order(poly_result["order_id"])
        elif kalshi_unfilled:
            # Poly filled but Kalshi didn't — risky, cancel Kalshi
            execution["status"] = "partial_poly_only"
            print("  [WARN] Only Poly filled! Cancelling Kalshi...")
            kalshi_cancel_order(kalshi_result["order_id"])
        elif poly_unfilled:
            # Kalshi filled but Poly didn't — risky, cancel Poly
            execution["status"] = "partial_kalshi_only"
            print("  [WARN] Only Kalshi filled! Cancelling Poly...")
            poly_cancel_order(poly_result["order_id"])
    else:
        execution["status"] = "dry_run"
        execution["kalshi_fill"] = {"filled": True, "status": "simulated"}
        execution["poly_fill"] = {"filled": True, "status": "simulated"}
        print("  [DRY RUN] Both legs simulated")

    _log_trade(execution)
    return execution


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_arbitrage_check():
    """Run a single arbitrage detection + execution cycle.

    Returns:
        dict with opportunities, executed_trades, errors
    """
    result = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "opportunities": [],
        "executed_trades": [],
        "errors": [],
    }

    # Fetch data from both platforms
    poly_data, poly_err = fetch_polymarket_data_struct()
    kalshi_data, kalshi_err = fetch_kalshi_data_struct()

    if poly_err:
        result["errors"].append(f"Polymarket: {poly_err}")
    if kalshi_err:
        result["errors"].append(f"Kalshi: {kalshi_err}")

    if not poly_data or not kalshi_data:
        return result

    # Find opportunities
    opportunities, _ = find_opportunities(poly_data, kalshi_data)
    result["opportunities"] = opportunities

    if not opportunities:
        return result

    # Pre-flight balance check (once per cycle, not per trade)
    balances = check_balances()
    if balances["errors"]:
        for err in balances["errors"]:
            print(f"  [BALANCE WARN] {err}")

    # Execute qualifying trades
    for opp in opportunities:
        if opp["margin"] < MIN_MARGIN:
            continue

        # Balance check
        ok, reason = _has_sufficient_funds(balances, opp)
        if not ok:
            print(f"  [SKIP] Insufficient funds: {reason}")
            result["errors"].append(f"Insufficient funds: {reason}")
            continue

        execution = execute_trade(opp)
        result["executed_trades"].append(execution)

    return result


def main():
    """Main trading loop."""
    print(f"Starting dual-leg arbitrage bot at {datetime.datetime.now(datetime.timezone.utc)}")
    print()

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            print(f"--- Cycle {cycle_count} at {now} ---")

            result = run_arbitrage_check()

            # Report errors
            if result["errors"]:
                for err in result["errors"]:
                    print(f"  ERROR: {err}")

            # Report opportunities
            if result["opportunities"]:
                qualifying = [
                    o for o in result["opportunities"]
                    if o["margin"] >= MIN_MARGIN
                ]
                print(
                    f"Found {len(result['opportunities'])} opportunities "
                    f"({len(qualifying)} above {MIN_MARGIN:.1%} threshold):"
                )
                for opp in result["opportunities"]:
                    flag = " ***" if opp["margin"] >= MIN_MARGIN else ""
                    print(
                        f"  {opp['type']}: "
                        f"strike=${opp['kalshi_strike']:,.0f}, "
                        f"margin={opp['margin']:.4f} "
                        f"(cost ${opp['total_cost']:.4f}){flag}"
                    )
            else:
                print("No arbitrage opportunities found")

            # Report executed trades
            if result["executed_trades"]:
                print(f"Executed {len(result['executed_trades'])} trades:")
                for trade in result["executed_trades"]:
                    status = trade["status"]
                    print(f"  [{status}]", end="")
                    if trade.get("kalshi_order"):
                        ko = trade["kalshi_order"]
                        oid = ko.get("order_id", "?")
                        print(f" Kalshi={oid}", end="")
                    if trade.get("poly_order"):
                        po = trade["poly_order"]
                        oid = po.get("order_id", "?")
                        print(f" Poly={oid}", end="")
                    print()

            print()
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nShutdown requested. Exiting.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
