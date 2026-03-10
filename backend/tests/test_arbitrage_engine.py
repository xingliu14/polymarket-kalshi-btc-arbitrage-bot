"""Tests for arbitrage detection engine."""

import unittest
from arbitrage.engine import find_opportunities
from kalshi.trader import calculate_kalshi_fee
from polymarket.trader import calculate_poly_fee


class TestArbitrageEngine(unittest.TestCase):
    """Test arbitrage opportunity detection."""

    def test_poly_greater_than_kalshi(self):
        """Test case: Poly strike > Kalshi strike."""
        poly_data = {
            "price_to_beat": 50000.0,
            "prices": {"Up": 0.50, "Down": 0.40}
        }
        kalshi_data = {
            "markets": [
                {
                    "ticker": "M1",
                    "strike": 45000.0,
                    "yes_ask": 30,
                    "no_ask": 70,
                    "yes_bid": 25,
                    "no_bid": 65,
                    "subtitle": "$45,000 or above"
                }
            ]
        }

        opportunities, _ = find_opportunities(poly_data, kalshi_data)

        self.assertGreater(len(opportunities), 0)
        opp = opportunities[0]
        self.assertEqual(opp["poly_leg"], "Down")
        self.assertEqual(opp["kalshi_leg"], "Yes")

    def test_poly_less_than_kalshi(self):
        """Test case: Poly strike < Kalshi strike."""
        poly_data = {
            "price_to_beat": 40000.0,
            "prices": {"Up": 0.45, "Down": 0.35}
        }
        kalshi_data = {
            "markets": [
                {
                    "ticker": "M1",
                    "strike": 45000.0,
                    "yes_ask": 30,
                    "no_ask": 20,
                    "yes_bid": 25,
                    "no_bid": 15,
                    "subtitle": "$45,000 or above"
                }
            ]
        }

        opportunities, _ = find_opportunities(poly_data, kalshi_data)

        self.assertGreater(len(opportunities), 0)
        opp = opportunities[0]
        self.assertEqual(opp["poly_leg"], "Up")
        self.assertEqual(opp["kalshi_leg"], "No")

    def test_equal_strikes(self):
        """Test case: Poly strike == Kalshi strike."""
        poly_data = {
            "price_to_beat": 50000.0,
            "prices": {"Up": 0.50, "Down": 0.40}
        }
        kalshi_data = {
            "markets": [
                {
                    "ticker": "M1",
                    "strike": 50000.0,
                    "yes_ask": 30,
                    "no_ask": 70,
                    "yes_bid": 25,
                    "no_bid": 65,
                    "subtitle": "$50,000 or above"
                }
            ]
        }

        opportunities, checks = find_opportunities(poly_data, kalshi_data)

        # Should have two checks for equal strikes
        self.assertEqual(len(checks), 2)

    def test_no_opportunity_when_costly(self):
        """Test: total_cost > 1.00 means no arbitrage."""
        poly_data = {
            "price_to_beat": 50000.0,
            "prices": {"Up": 0.70, "Down": 0.70}
        }
        kalshi_data = {
            "markets": [
                {
                    "ticker": "M1",
                    "strike": 45000.0,
                    "yes_ask": 50,
                    "no_ask": 50,
                    "yes_bid": 45,
                    "no_bid": 45,
                    "subtitle": "$45,000 or above"
                }
            ]
        }

        opportunities, _ = find_opportunities(poly_data, kalshi_data)

        self.assertEqual(len(opportunities), 0)

    def test_arbitrage_found_when_cheap(self):
        """Test: total_cost < 1.00 means arbitrage."""
        poly_data = {
            "price_to_beat": 50000.0,
            "prices": {"Up": 0.40, "Down": 0.30}
        }
        kalshi_data = {
            "markets": [
                {
                    "ticker": "M1",
                    "strike": 45000.0,
                    "yes_ask": 20,
                    "no_ask": 20,
                    "yes_bid": 15,
                    "no_bid": 15,
                    "subtitle": "$45,000 or above"
                }
            ]
        }

        opportunities, _ = find_opportunities(poly_data, kalshi_data)

        self.assertGreater(len(opportunities), 0)
        opp = opportunities[0]
        self.assertTrue(opp["is_arbitrage"])
        self.assertGreater(opp["margin"], 0)

    def test_selects_9_nearest_markets(self):
        """Test that algorithm selects up to 9 markets nearest the strike."""
        poly_data = {
            "price_to_beat": 50000.0,
            "prices": {"Up": 0.50, "Down": 0.40}
        }
        # Create 20 markets
        markets = [
            {
                "ticker": f"M{i}",
                "strike": 30000.0 + i * 1000.0,
                "yes_ask": 30,
                "no_ask": 70,
                "yes_bid": 25,
                "no_bid": 65,
                "subtitle": f"${30000 + i * 1000} or above"
            }
            for i in range(20)
        ]
        kalshi_data = {"markets": markets}

        _, checks = find_opportunities(poly_data, kalshi_data)

        # Should have at most 9 checks (could be less if less than 9 markets exist)
        self.assertLessEqual(len(checks), 9)

    def test_empty_data_returns_empty_list(self):
        """Test that empty data returns empty opportunity list."""
        poly_data = None
        kalshi_data = {"markets": []}

        opportunities, checks = find_opportunities(poly_data, kalshi_data)

        self.assertEqual(len(opportunities), 0)
        self.assertEqual(len(checks), 0)


class TestPolymarketFees(unittest.TestCase):
    """Test Polymarket fee calculation."""

    def test_crypto_fee_at_50_cents(self):
        """Max effective fee at p=0.50 should be ~1.56%."""
        fee = calculate_poly_fee(price=0.50, size=1.0, category="crypto")
        # fee = 1 * 0.50 * 0.25 * (0.50 * 0.50)^2 = 0.125 * 0.0625 = 0.0078125
        self.assertAlmostEqual(fee, 0.0078125)
        # Effective rate = fee / price = 0.0078125 / 0.50 = 1.5625%
        self.assertAlmostEqual(fee / 0.50, 0.015625, places=4)

    def test_crypto_fee_at_extreme_prices(self):
        """Fee should be near zero at extreme prices (close to 0 or 1)."""
        fee_low = calculate_poly_fee(price=0.05, size=1.0, category="crypto")
        fee_high = calculate_poly_fee(price=0.95, size=1.0, category="crypto")
        self.assertLess(fee_low, 0.001)
        self.assertLess(fee_high, 0.001)

    def test_fee_scales_with_size(self):
        """Fee should scale linearly with size."""
        fee_1 = calculate_poly_fee(price=0.50, size=1.0)
        fee_10 = calculate_poly_fee(price=0.50, size=10.0)
        self.assertAlmostEqual(fee_10, fee_1 * 10)

    def test_maker_pays_no_fee(self):
        """Makers pay zero fees."""
        fee = calculate_poly_fee(price=0.50, size=1.0, is_maker=True)
        self.assertEqual(fee, 0.0)

    def test_sports_fee_lower_than_crypto(self):
        """Sports fee should be lower than crypto at same price."""
        crypto_fee = calculate_poly_fee(price=0.50, size=1.0, category="crypto")
        sports_fee = calculate_poly_fee(price=0.50, size=1.0, category="sports")
        self.assertGreater(crypto_fee, sports_fee)

    def test_unknown_category_returns_zero(self):
        """Unknown category returns 0 fee."""
        fee = calculate_poly_fee(price=0.50, size=1.0, category="unknown")
        self.assertEqual(fee, 0.0)


class TestArbitrageEngineWithFees(unittest.TestCase):
    """Test that fees are correctly integrated into arbitrage detection."""

    def test_opportunity_includes_fee_fields(self):
        """Opportunities should include poly_fee, kalshi_fee, and margin_before_fees."""
        poly_data = {
            "price_to_beat": 50000.0,
            "prices": {"Up": 0.40, "Down": 0.30},
            "token_ids": {"Up": "t1", "Down": "t2"},
        }
        kalshi_data = {
            "markets": [{
                "ticker": "M1", "strike": 45000.0,
                "yes_ask": 20, "no_ask": 20,
                "yes_bid": 15, "no_bid": 15,
                "subtitle": "$45,000 or above",
            }]
        }
        opportunities, _ = find_opportunities(poly_data, kalshi_data)
        self.assertGreater(len(opportunities), 0)
        opp = opportunities[0]
        self.assertIn("poly_fee", opp)
        self.assertIn("kalshi_fee", opp)
        self.assertIn("margin_before_fees", opp)
        self.assertGreater(opp["poly_fee"], 0)
        self.assertGreater(opp["kalshi_fee"], 0)
        self.assertGreater(opp["margin_before_fees"], opp["margin"])

    def test_fee_eliminates_thin_arbitrage(self):
        """A very thin margin should be eliminated by fees."""
        # poly_cost=0.50, kalshi_cost=0.49 → margin_before_fees=0.01
        # poly_fee at 0.50 = 0.0078125 → margin = 0.01 - 0.0078 = 0.0022
        # Still positive but much thinner.
        # With poly_cost=0.50, kalshi_cost=0.495 → margin_before_fees=0.005
        # margin = 0.005 - 0.0078 = -0.0028 → no arbitrage!
        poly_data = {
            "price_to_beat": 50000.0,
            "prices": {"Up": 0.50, "Down": 0.50},
            "token_ids": {"Up": "t1", "Down": "t2"},
        }
        kalshi_data = {
            "markets": [{
                "ticker": "M1", "strike": 45000.0,
                "yes_ask": 50, "no_ask": 50,  # kalshi_cost = 0.50
                "yes_bid": 45, "no_bid": 45,
                "subtitle": "$45,000 or above",
            }]
        }
        # total_cost = 0.50 + 0.50 = 1.00, margin_before_fees = 0.00
        # With fee, margin < 0 → no arbitrage
        opportunities, checks = find_opportunities(poly_data, kalshi_data)
        self.assertEqual(len(opportunities), 0)
        # But check should still exist
        self.assertGreater(len(checks), 0)
        self.assertFalse(checks[0]["is_arbitrage"])


class TestKalshiFees(unittest.TestCase):
    """Test Kalshi fee calculation per the fee schedule."""

    def test_taker_fee_at_50_cents(self):
        """At $0.50, fee for 1 contract = ceil(0.07 * 1 * 0.5 * 0.5) = ceil(0.0175) = $0.02."""
        fee = calculate_kalshi_fee(price_cents=50, count=1)
        self.assertEqual(fee, 0.02)

    def test_taker_fee_at_10_cents(self):
        """At $0.10, fee for 1 contract = ceil(0.07 * 1 * 0.1 * 0.9) = ceil(0.0063) = $0.01."""
        fee = calculate_kalshi_fee(price_cents=10, count=1)
        self.assertEqual(fee, 0.01)

    def test_taker_fee_100_contracts_at_50_cents(self):
        """At $0.50, fee for 100 = ceil(0.07 * 100 * 0.5 * 0.5) = $1.75."""
        fee = calculate_kalshi_fee(price_cents=50, count=100)
        self.assertEqual(fee, 1.75)

    def test_taker_fee_at_20_cents(self):
        """At $0.20, fee for 1 contract = ceil(0.07 * 1 * 0.2 * 0.8 * 100)/100 = $0.02."""
        fee = calculate_kalshi_fee(price_cents=20, count=1)
        self.assertEqual(fee, 0.02)

    def test_maker_fee_at_50_cents(self):
        """Maker at $0.50: ceil(0.0175 * 1 * 0.5 * 0.5) = ceil(0.004375) = $0.01."""
        fee = calculate_kalshi_fee(price_cents=50, count=1, is_maker=True)
        self.assertEqual(fee, 0.01)

    def test_fee_matches_schedule_table(self):
        """Verify against published fee table values for 100 contracts."""
        # (price_cents, expected_fee_dollars_for_100_contracts)
        table = [
            (1, 0.07), (5, 0.34), (10, 0.63), (15, 0.90),
            (20, 1.12), (25, 1.32), (30, 1.47), (35, 1.60),
            (40, 1.68), (45, 1.74), (50, 1.75), (55, 1.74),
            (60, 1.68), (65, 1.60), (70, 1.47), (75, 1.32),
            (80, 1.12), (85, 0.90), (90, 0.63), (95, 0.34),
            (99, 0.07),
        ]
        for price_cents, expected in table:
            with self.subTest(price_cents=price_cents):
                fee = calculate_kalshi_fee(price_cents=price_cents, count=100)
                self.assertEqual(fee, expected, f"Failed at {price_cents}c")


if __name__ == "__main__":
    unittest.main()
