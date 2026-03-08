"""Tests for arbitrage detection engine."""

import unittest
from arbitrage.engine import find_opportunities


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


if __name__ == "__main__":
    unittest.main()
