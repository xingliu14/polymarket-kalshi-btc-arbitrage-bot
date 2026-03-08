"""Tests for Polymarket order placement."""

import unittest
from unittest.mock import patch, MagicMock
from polymarket.trader import place_order, get_order_status, cancel_order


class TestPlaceOrder(unittest.TestCase):
    """Test order placement."""

    def test_place_order_dry_run(self):
        """Test that dry_run doesn't make any HTTP/SDK call."""
        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=0.50,
            size=10,
            dry_run=True,
        )

        self.assertTrue(result["success"])
        self.assertIn("SIMULATED_POLY", result["order_id"])
        self.assertIsNone(result["error"])

    def test_place_order_dry_run_case_insensitive(self):
        """Test that side is case-insensitive."""
        result = place_order(
            token_id="abc123token",
            side="buy",
            price=0.50,
            size=10,
            dry_run=True,
        )

        self.assertTrue(result["success"])

    def test_place_order_invalid_side(self):
        """Test that invalid side fails."""
        result = place_order(
            token_id="abc123token",
            side="HOLD",
            price=0.50,
            size=10,
        )

        self.assertFalse(result["success"])
        self.assertIn("Invalid side", result["error"])

    def test_place_order_price_too_low(self):
        """Test that price <= 0 fails."""
        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=0.0,
            size=10,
        )

        self.assertFalse(result["success"])
        self.assertIn("outside valid range", result["error"])

    def test_place_order_price_too_high(self):
        """Test that price >= 1 fails."""
        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=1.0,
            size=10,
        )

        self.assertFalse(result["success"])
        self.assertIn("outside valid range", result["error"])

    def test_place_order_negative_size(self):
        """Test that size <= 0 fails."""
        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=0.50,
            size=0,
        )

        self.assertFalse(result["success"])
        self.assertIn("Size must be positive", result["error"])

    @patch("polymarket.trader.SDK_AVAILABLE", False)
    def test_place_order_no_sdk(self):
        """Test that missing SDK returns clear error."""
        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=0.50,
            size=10,
            dry_run=False,
        )

        self.assertFalse(result["success"])
        self.assertIn("py-clob-client", result["error"])

    @patch("polymarket.trader._place_order_sdk")
    @patch("polymarket.trader.SDK_AVAILABLE", True)
    def test_place_order_missing_credentials(self, mock_sdk):
        """Test that missing credentials returns error."""
        mock_sdk.return_value = {
            "success": False,
            "order_id": None,
            "error": "Missing Polymarket credentials. Check env vars.",
        }

        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=0.50,
            size=10,
            dry_run=False,
        )

        self.assertFalse(result["success"])
        self.assertIn("credentials", result["error"].lower())

    @patch("polymarket.trader._place_order_sdk")
    @patch("polymarket.trader.SDK_AVAILABLE", True)
    def test_place_order_sdk_success(self, mock_sdk):
        """Test successful order via SDK."""
        mock_sdk.return_value = {
            "success": True,
            "order_id": "0xorder123",
            "error": None,
        }

        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=0.50,
            size=10,
            dry_run=False,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["order_id"], "0xorder123")
        mock_sdk.assert_called_once_with(
            "abc123token", "BUY", 0.50, 10, "0.01", False, "GTC"
        )

    @patch("polymarket.trader._place_order_sdk")
    @patch("polymarket.trader.SDK_AVAILABLE", True)
    def test_place_order_sdk_failure(self, mock_sdk):
        """Test SDK order failure returns error."""
        mock_sdk.return_value = {
            "success": False,
            "order_id": None,
            "error": "Insufficient balance",
        }

        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=0.50,
            size=10,
            dry_run=False,
        )

        self.assertFalse(result["success"])
        self.assertIn("Insufficient balance", result["error"])

    @patch("polymarket.trader._place_order_sdk")
    @patch("polymarket.trader.SDK_AVAILABLE", True)
    def test_place_order_sdk_network_error(self, mock_sdk):
        """Test that SDK errors are returned properly."""
        mock_sdk.return_value = {
            "success": False,
            "order_id": None,
            "error": "Network error",
        }

        result = place_order(
            token_id="abc123token",
            side="BUY",
            price=0.50,
            size=10,
            dry_run=False,
        )

        self.assertFalse(result["success"])
        self.assertIn("Network error", result["error"])

    @patch("polymarket.trader._place_order_sdk")
    @patch("polymarket.trader.SDK_AVAILABLE", True)
    def test_place_sell_order(self, mock_sdk):
        """Test SELL order passes correct side to SDK."""
        mock_sdk.return_value = {
            "success": True,
            "order_id": "0xsell123",
            "error": None,
        }

        result = place_order(
            token_id="abc123token",
            side="SELL",
            price=0.60,
            size=5,
            dry_run=False,
        )

        self.assertTrue(result["success"])
        mock_sdk.assert_called_once_with(
            "abc123token", "SELL", 0.60, 5, "0.01", False, "GTC"
        )


class TestGetOrderStatus(unittest.TestCase):
    """Test order status fetching."""

    @patch("polymarket.trader.requests.get")
    @patch("polymarket.trader.get_l2_headers")
    def test_get_order_status_success(self, mock_headers, mock_get):
        """Test successful order status fetch."""
        mock_headers.return_value = {"POLY_API_KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "0xorder123",
            "status": "live",
            "side": "BUY",
        }
        mock_get.return_value = mock_response

        result = get_order_status("0xorder123")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "live")

    @patch("polymarket.trader.requests.get")
    @patch("polymarket.trader.get_l2_headers")
    def test_get_order_status_not_found(self, mock_headers, mock_get):
        """Test order not found."""
        mock_headers.return_value = {"POLY_API_KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Order not found"
        mock_get.return_value = mock_response

        result = get_order_status("0xbadorder")

        self.assertFalse(result["success"])
        self.assertIn("404", result["error"])


class TestCancelOrder(unittest.TestCase):
    """Test order cancellation."""

    def test_cancel_order_dry_run(self):
        """Test that dry_run doesn't make HTTP call."""
        result = cancel_order("0xorder123", dry_run=True)
        self.assertTrue(result["success"])

    @patch("polymarket.trader.requests.delete")
    @patch("polymarket.trader.get_l2_headers")
    def test_cancel_order_success(self, mock_headers, mock_delete):
        """Test successful order cancellation."""
        mock_headers.return_value = {"POLY_API_KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "canceled": ["0xorder123"],
            "not_canceled": {},
        }
        mock_delete.return_value = mock_response

        result = cancel_order("0xorder123")

        self.assertTrue(result["success"])

    @patch("polymarket.trader.requests.delete")
    @patch("polymarket.trader.get_l2_headers")
    def test_cancel_order_not_canceled(self, mock_headers, mock_delete):
        """Test order that couldn't be canceled."""
        mock_headers.return_value = {"POLY_API_KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "canceled": [],
            "not_canceled": {"0xorder123": "Order already filled"},
        }
        mock_delete.return_value = mock_response

        result = cancel_order("0xorder123")

        self.assertFalse(result["success"])
        self.assertIn("already filled", result["error"])

    @patch("polymarket.trader.requests.delete")
    @patch("polymarket.trader.get_l2_headers")
    def test_cancel_order_api_error(self, mock_headers, mock_delete):
        """Test API error during cancellation."""
        mock_headers.return_value = {"POLY_API_KEY": "test"}
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_delete.return_value = mock_response

        result = cancel_order("0xorder123")

        self.assertFalse(result["success"])
        self.assertIn("401", result["error"])


if __name__ == "__main__":
    unittest.main()
