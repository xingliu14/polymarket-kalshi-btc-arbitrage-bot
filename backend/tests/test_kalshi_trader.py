"""Tests for Kalshi order placement."""

import unittest
from unittest.mock import patch, MagicMock
from kalshi.trader import place_order, get_balance, cancel_order


class TestPlaceOrder(unittest.TestCase):
    """Test order placement."""

    def test_place_order_dry_run(self):
        """Test that dry_run doesn't make HTTP call."""
        result = place_order(
            ticker="KXBTCD-250307-14",
            side="yes",
            action="buy",
            count=1,
            yes_price_cents=50,
            dry_run=True
        )

        self.assertTrue(result["success"])
        self.assertIsNotNone(result["order_id"])

    def test_place_order_invalid_price_low(self):
        """Test that price < 1 fails immediately."""
        result = place_order(
            ticker="KXBTCD-250307-14",
            side="yes",
            action="buy",
            count=1,
            yes_price_cents=0,
            dry_run=False
        )

        self.assertFalse(result["success"])
        self.assertIn("outside 1-99", result["error"])

    def test_place_order_invalid_price_high(self):
        """Test that price > 99 fails immediately."""
        result = place_order(
            ticker="KXBTCD-250307-14",
            side="yes",
            action="buy",
            count=1,
            yes_price_cents=100,
            dry_run=False
        )

        self.assertFalse(result["success"])
        self.assertIn("outside 1-99", result["error"])

    @patch("kalshi.trader.requests.post")
    @patch("kalshi.trader.get_auth_headers")
    def test_place_order_success(self, mock_auth, mock_post):
        """Test successful order placement."""
        mock_auth.return_value = {"KALSHI-ACCESS-KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"order": {"order_id": "order_123"}}
        mock_post.return_value = mock_response

        result = place_order(
            ticker="KXBTCD-250307-14",
            side="yes",
            action="buy",
            count=1,
            yes_price_cents=50,
            dry_run=False
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["order_id"], "order_123")

    @patch("kalshi.trader.requests.post")
    @patch("kalshi.trader.get_auth_headers")
    def test_place_order_api_error(self, mock_auth, mock_post):
        """Test handling of API error."""
        mock_auth.return_value = {"KALSHI-ACCESS-KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response

        result = place_order(
            ticker="KXBTCD-250307-14",
            side="yes",
            action="buy",
            count=1,
            yes_price_cents=50,
            dry_run=False
        )

        self.assertFalse(result["success"])
        self.assertIn("400", result["error"])


class TestGetBalance(unittest.TestCase):
    """Test balance fetching."""

    @patch("kalshi.trader.requests.get")
    @patch("kalshi.trader.get_auth_headers")
    def test_get_balance_success(self, mock_auth, mock_get):
        """Test successful balance fetch."""
        mock_auth.return_value = {"KALSHI-ACCESS-KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"balance": 10000.0}
        mock_get.return_value = mock_response

        result = get_balance()

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["balance"], 10000.0)


class TestCancelOrder(unittest.TestCase):
    """Test order cancellation."""

    def test_cancel_order_dry_run(self):
        """Test that dry_run doesn't make HTTP call."""
        result = cancel_order("order_123", dry_run=True)
        self.assertTrue(result["success"])

    @patch("kalshi.trader.requests.delete")
    @patch("kalshi.trader.get_auth_headers")
    def test_cancel_order_success(self, mock_auth, mock_delete):
        """Test successful order cancellation."""
        mock_auth.return_value = {"KALSHI-ACCESS-KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_delete.return_value = mock_response

        result = cancel_order("order_123", dry_run=False)

        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
