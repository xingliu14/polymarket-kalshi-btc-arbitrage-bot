"""Arbitrage detection engine.

Detects profitable arbitrage opportunities between Polymarket and Kalshi BTC markets.
"""


def find_opportunities(poly_data: dict, kalshi_data: dict) -> tuple[list, list]:
    """Find arbitrage opportunities between Polymarket and Kalshi.

    Args:
        poly_data: Polymarket data dict with keys: price_to_beat, prices (dict)
        kalshi_data: Kalshi data dict with keys: markets (list)

    Returns:
        (opportunities, checks) - lists of dicts
        opportunities: List of arbitrage opportunities (is_arbitrage=True, margin > 0)
        checks: All market checks performed (for logging/debugging)
    """
    opportunities = []
    checks = []

    # Validate inputs
    if not poly_data or not kalshi_data:
        return opportunities, checks

    poly_strike = poly_data.get("price_to_beat")
    poly_prices = poly_data.get("prices", {})
    poly_up_cost = poly_prices.get("Up", 0.0)
    poly_down_cost = poly_prices.get("Down", 0.0)

    if poly_strike is None:
        return opportunities, checks

    # Select relevant Kalshi markets (4 below, 4 above)
    kalshi_markets = kalshi_data.get("markets", [])
    if not kalshi_markets:
        return opportunities, checks

    kalshi_markets_sorted = sorted(kalshi_markets, key=lambda x: x["strike"])

    # Find index closest to poly_strike
    closest_idx = 0
    min_diff = float("inf")
    for i, m in enumerate(kalshi_markets_sorted):
        diff = abs(m["strike"] - poly_strike)
        if diff < min_diff:
            min_diff = diff
            closest_idx = i

    # Select 4 below and 4 above (up to 9 total)
    start_idx = max(0, closest_idx - 4)
    end_idx = min(len(kalshi_markets_sorted), closest_idx + 5)
    selected_markets = kalshi_markets_sorted[start_idx:end_idx]

    # Check each market for arbitrage
    for km in selected_markets:
        kalshi_strike = km["strike"]
        kalshi_yes_cost = km["yes_ask"] / 100.0
        kalshi_no_cost = km["no_ask"] / 100.0

        # Determine which pair to check based on strike relationship
        checks_to_perform = []

        if poly_strike > kalshi_strike:
            checks_to_perform.append({
                "type": "Poly > Kalshi",
                "poly_leg": "Down",
                "kalshi_leg": "Yes",
                "poly_cost": poly_down_cost,
                "kalshi_cost": kalshi_yes_cost,
            })
        elif poly_strike < kalshi_strike:
            checks_to_perform.append({
                "type": "Poly < Kalshi",
                "poly_leg": "Up",
                "kalshi_leg": "No",
                "poly_cost": poly_up_cost,
                "kalshi_cost": kalshi_no_cost,
            })
        elif poly_strike == kalshi_strike:
            checks_to_perform.append({
                "type": "Equal (Down)",
                "poly_leg": "Down",
                "kalshi_leg": "Yes",
                "poly_cost": poly_down_cost,
                "kalshi_cost": kalshi_yes_cost,
            })
            checks_to_perform.append({
                "type": "Equal (Up)",
                "poly_leg": "Up",
                "kalshi_leg": "No",
                "poly_cost": poly_up_cost,
                "kalshi_cost": kalshi_no_cost,
            })

        for check in checks_to_perform:
            total_cost = check["poly_cost"] + check["kalshi_cost"]
            margin = 1.00 - total_cost

            opportunity = {
                "kalshi_strike": kalshi_strike,
                "type": check["type"],
                "poly_leg": check["poly_leg"],
                "kalshi_leg": check["kalshi_leg"],
                "poly_cost": check["poly_cost"],
                "kalshi_cost": check["kalshi_cost"],
                "total_cost": total_cost,
                "margin": margin,
                "is_arbitrage": total_cost < 1.00,
                "kalshi_market": km,
            }

            checks.append(opportunity)

            if opportunity["is_arbitrage"]:
                opportunities.append(opportunity)

    return opportunities, checks
