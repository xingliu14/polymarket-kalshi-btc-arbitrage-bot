"""Tests for Polymarket market data fetching."""

import unittest
from unittest.mock import patch, MagicMock
from polymarket.markets import get_clob_price, get_polymarket_data, fetch_polymarket_data_struct


class TestGetClobPrice(unittest.TestCase):
    """Test CLOB price fetching."""

    @patch("polymarket.markets.requests.get")
    def test_get_clob_price_success(self, mock_get):
        """Test successful price fetch."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bids": [{"price": "0.38", "size": "100"}],
            "asks": [{"price": "0.42", "size": "100"}]
        }
        mock_get.return_value = mock_response

        price = get_clob_price("token_123")

        self.assertEqual(price, 0.42)

    @patch("polymarket.markets.requests.get")
    def test_get_clob_price_empty_book(self, mock_get):
        """Test handling of empty orderbook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bids": [], "asks": []}
        mock_get.return_value = mock_response

        price = get_clob_price("token_123")

        self.assertEqual(price, 0.0)

    @patch("polymarket.markets.requests.get")
    def test_get_clob_price_api_error(self, mock_get):
        """Test handling of API error."""
        mock_get.side_effect = Exception("Connection error")

        price = get_clob_price("token_123")

        self.assertIsNone(price)


class TestGetPolymarketData(unittest.TestCase):
    """Test Polymarket event data fetching."""

    @patch("polymarket.markets.get_clob_price")
    @patch("polymarket.markets.requests.get")
    def test_get_polymarket_data_success(self, mock_get, mock_clob):
        """Test successful data fetch."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "markets": [
                    {
                        "clobTokenIds": '["token_up", "token_down"]',
                        "outcomes": '["Up", "Down"]'
                    }
                ]
            }
        ]
        mock_get.return_value = mock_response
        mock_clob.side_effect = [0.55, 0.45]

        prices, err = get_polymarket_data("bitcoin-slug")

        self.assertIsNone(err)
        self.assertEqual(prices["Up"], 0.55)
        self.assertEqual(prices["Down"], 0.45)

    @patch("polymarket.markets.requests.get")
    def test_get_polymarket_data_not_found(self, mock_get):
        """Test handling of missing event."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        prices, err = get_polymarket_data("nonexistent-slug")

        self.assertIsNotNone(err)
        self.assertIn("not found", err)


class TestFetchPolymarketDataStruct(unittest.TestCase):
    """Test Polymarket data structuring."""

    @patch("polymarket.markets.get_binance_open_price")
    @patch("polymarket.markets.get_binance_current_price")
    @patch("polymarket.markets.get_polymarket_data")
    @patch("polymarket.markets.get_current_market_urls")
    def test_fetch_polymarket_data_struct_success(
        self, mock_urls, mock_poly, mock_binance_current, mock_binance_open
    ):
        """Test successful data fetch and structuring."""
        mock_urls.return_value = {
            "polymarket": "https://polymarket.com/event/bitcoin-slug",
            "target_time_utc": MagicMock()
        }
        mock_poly.return_value = ({"Up": 0.55, "Down": 0.45}, None)
        mock_binance_current.return_value = (50000.0, None)
        mock_binance_open.return_value = (49500.0, None)

        data, err = fetch_polymarket_data_struct()

        self.assertIsNone(err)
        self.assertEqual(data["price_to_beat"], 49500.0)
        self.assertEqual(data["current_price"], 50000.0)
        self.assertEqual(data["prices"]["Up"], 0.55)
        self.assertEqual(data["slug"], "bitcoin-slug")


if __name__ == "__main__":
    unittest.main()
