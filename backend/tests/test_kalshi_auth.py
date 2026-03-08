"""Tests for Kalshi authentication."""

import unittest
from unittest.mock import patch, MagicMock
import base64
from kalshi.auth import get_auth_headers, load_private_key


class TestKalshiAuth(unittest.TestCase):
    """Test Kalshi RSA-PSS authentication."""

    @patch("kalshi.auth.load_private_key")
    @patch("kalshi.auth.time.time")
    def test_get_auth_headers_returns_required_keys(self, mock_time, mock_load_key):
        """Verify that get_auth_headers returns all required header keys."""
        mock_time.return_value = 1234567890.0

        mock_key = MagicMock()
        mock_key.sign.return_value = b"mock_signature"
        mock_load_key.return_value = mock_key

        headers = get_auth_headers("GET", "/test/path")

        self.assertIn("KALSHI-ACCESS-KEY", headers)
        self.assertIn("KALSHI-ACCESS-TIMESTAMP", headers)
        self.assertIn("KALSHI-ACCESS-SIGNATURE", headers)
        self.assertIn("Content-Type", headers)
        self.assertEqual(headers["Content-Type"], "application/json")

    @patch("kalshi.auth.load_private_key")
    @patch("kalshi.auth.time.time")
    def test_signature_is_base64(self, mock_time, mock_load_key):
        """Verify that signature is valid base64."""
        mock_time.return_value = 1234567890.0

        mock_key = MagicMock()
        mock_key.sign.return_value = b"mock_binary_signature"
        mock_load_key.return_value = mock_key

        headers = get_auth_headers("POST", "/trade-api/v2/portfolio/orders")

        try:
            base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        except Exception as e:
            self.fail(f"Signature is not valid base64: {e}")

    @patch("builtins.open", side_effect=FileNotFoundError("No such file"))
    def test_missing_key_file_raises(self, mock_open):
        """Verify that missing key file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_private_key()

    @patch("kalshi.auth.load_private_key")
    @patch("kalshi.auth.time.time")
    def test_timestamp_included(self, mock_time, mock_load_key):
        """Verify that timestamp is included in headers."""
        mock_time.return_value = 1500000000.0

        mock_key = MagicMock()
        mock_key.sign.return_value = b"sig"
        mock_load_key.return_value = mock_key

        headers = get_auth_headers("GET", "/path")

        self.assertEqual(headers["KALSHI-ACCESS-TIMESTAMP"], "1500000000000")


if __name__ == "__main__":
    unittest.main()
