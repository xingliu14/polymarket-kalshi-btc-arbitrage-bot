"""Tests for Kalshi market data fetching."""

import unittest
from unittest.mock import patch, MagicMock
from kalshi.markets import parse_strike, fetch_kalshi_data_struct


class TestParseStrike(unittest.TestCase):
    """Test strike price parsing from subtitles."""

    def test_parse_strike_above(self):
        """Test parsing '$96,250 or above'."""
        result = parse_strike("$96,250 or above")
        self.assertEqual(result, 96250.0)

    def test_parse_strike_at_or_above(self):
        """Test parsing '$97,000 at or above'."""
        result = parse_strike("$97,000 at or above")
        self.assertEqual(result, 97000.0)

    def test_parse_strike_no_commas(self):
        """Test parsing without commas."""
        result = parse_strike("$50000 or above")
        self.assertEqual(result, 50000.0)

    def test_parse_strike_invalid(self):
        """Test parsing invalid string returns 0."""
        result = parse_strike("Invalid string")
        self.assertEqual(result, 0.0)

    def test_parse_strike_empty(self):
        """Test parsing empty string returns 0."""
        result = parse_strike("")
        self.assertEqual(result, 0.0)


class TestFetchKalshiDataStruct(unittest.TestCase):
    """Test Kalshi data fetching and structuring."""

    @patch("kalshi.markets.get_kalshi_markets")
    @patch("kalshi.markets.get_binance_current_price")
    @patch("kalshi.markets.get_current_market_urls")
    def test_fetch_kalshi_data_struct_success(self, mock_urls, mock_binance, mock_markets):
        """Test successful Kalshi data fetch."""
        mock_urls.return_value = {
            "kalshi": "https://kalshi.com/markets/kxbtcd/bitcoin-price-abovebelow/kxbtcd-25mar0614"
        }
        mock_binance.return_value = (50000.0, None)
        mock_markets.return_value = (
            [
                {
                    "ticker": "KXBTCD-250307-14",
                    "yes_bid": 20,
                    "yes_ask": 25,
                    "no_bid": 75,
                    "no_ask": 80,
                    "subtitle": "$50000 or above"
                }
            ],
            None
        )

        data, err = fetch_kalshi_data_struct()

        self.assertIsNone(err)
        self.assertIsNotNone(data)
        self.assertEqual(data["event_ticker"], "KXBTCD-25MAR0614")
        self.assertEqual(data["current_price"], 50000.0)
        self.assertEqual(len(data["markets"]), 1)
        self.assertEqual(data["markets"][0]["ticker"], "KXBTCD-250307-14")
        self.assertEqual(data["markets"][0]["strike"], 50000.0)

    @patch("kalshi.markets.get_kalshi_markets")
    @patch("kalshi.markets.get_binance_current_price")
    @patch("kalshi.markets.get_current_market_urls")
    def test_fetch_kalshi_data_struct_api_error(self, mock_urls, mock_binance, mock_markets):
        """Test handling of API error."""
        mock_urls.return_value = {
            "kalshi": "https://kalshi.com/markets/kxbtcd/bitcoin-price-abovebelow/test"
        }
        mock_binance.return_value = (None, "Connection error")
        mock_markets.return_value = (None, "API error")

        data, err = fetch_kalshi_data_struct()

        self.assertIsNotNone(err)
        self.assertIn("Kalshi Error", err)

    @patch("kalshi.markets.get_kalshi_markets")
    @patch("kalshi.markets.get_binance_current_price")
    @patch("kalshi.markets.get_current_market_urls")
    def test_fetch_kalshi_markets_sorted_by_strike(self, mock_urls, mock_binance, mock_markets):
        """Test that markets are sorted by strike."""
        mock_urls.return_value = {"kalshi": "https://kalshi.com/markets/kxbtcd/test"}
        mock_binance.return_value = (50000.0, None)
        mock_markets.return_value = (
            [
                {"ticker": "M1", "subtitle": "$60000 or above", "yes_bid": 10, "yes_ask": 15,
                 "no_bid": 85, "no_ask": 90},
                {"ticker": "M2", "subtitle": "$40000 or above", "yes_bid": 10, "yes_ask": 15,
                 "no_bid": 85, "no_ask": 90},
                {"ticker": "M3", "subtitle": "$50000 or above", "yes_bid": 10, "yes_ask": 15,
                 "no_bid": 85, "no_ask": 90},
            ],
            None
        )

        data, _ = fetch_kalshi_data_struct()

        strikes = [m["strike"] for m in data["markets"]]
        self.assertEqual(strikes, sorted(strikes))


if __name__ == "__main__":
    unittest.main()
