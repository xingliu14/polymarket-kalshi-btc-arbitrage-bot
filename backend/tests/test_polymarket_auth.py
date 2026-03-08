"""Tests for Polymarket authentication."""

import unittest
from unittest.mock import patch
from polymarket.auth import build_hmac_signature, get_l2_headers


class TestBuildHmacSignature(unittest.TestCase):
    """Test HMAC signature generation."""

    def test_signature_without_body(self):
        """Test signature for GET request (no body)."""
        # base64 encode a known secret
        import base64
        secret = base64.urlsafe_b64encode(b"testsecret123456").decode()

        sig = build_hmac_signature(secret, "1700000000", "GET", "/order/abc")

        self.assertIsInstance(sig, str)
        self.assertTrue(len(sig) > 0)

    def test_signature_with_body(self):
        """Test signature for POST request (with body)."""
        import base64
        secret = base64.urlsafe_b64encode(b"testsecret123456").decode()

        sig = build_hmac_signature(
            secret, "1700000000", "POST", "/order",
            body='{"tokenID": "abc123"}'
        )

        self.assertIsInstance(sig, str)
        self.assertTrue(len(sig) > 0)

    def test_different_inputs_produce_different_signatures(self):
        """Test that different timestamps produce different signatures."""
        import base64
        secret = base64.urlsafe_b64encode(b"testsecret123456").decode()

        sig1 = build_hmac_signature(secret, "1700000000", "GET", "/order")
        sig2 = build_hmac_signature(secret, "1700000001", "GET", "/order")

        self.assertNotEqual(sig1, sig2)

    def test_body_single_quotes_replaced(self):
        """Test that single quotes in body are replaced with double quotes."""
        import base64
        secret = base64.urlsafe_b64encode(b"testsecret123456").decode()

        # These should produce the same signature
        sig1 = build_hmac_signature(
            secret, "1700000000", "POST", "/order",
            body="{'key': 'value'}"
        )
        sig2 = build_hmac_signature(
            secret, "1700000000", "POST", "/order",
            body='{"key": "value"}'
        )

        self.assertEqual(sig1, sig2)


class TestGetL2Headers(unittest.TestCase):
    """Test L2 header generation."""

    @patch("polymarket.auth.POLY_FUNDER_ADDRESS", "0xTestAddress")
    @patch("polymarket.auth.POLY_API_KEY", "test-api-key")
    @patch("polymarket.auth.POLY_PASSPHRASE", "test-passphrase")
    @patch("polymarket.auth.POLY_API_SECRET", "dGVzdHNlY3JldDEyMzQ1Ng==")
    def test_headers_contain_required_fields(self):
        """Test that all required POLY headers are present."""
        headers = get_l2_headers("GET", "/order/abc")

        self.assertIn("POLY_ADDRESS", headers)
        self.assertIn("POLY_SIGNATURE", headers)
        self.assertIn("POLY_TIMESTAMP", headers)
        self.assertIn("POLY_API_KEY", headers)
        self.assertIn("POLY_PASSPHRASE", headers)
        self.assertIn("Content-Type", headers)

    @patch("polymarket.auth.POLY_FUNDER_ADDRESS", "0xTestAddress")
    @patch("polymarket.auth.POLY_API_KEY", "test-api-key")
    @patch("polymarket.auth.POLY_PASSPHRASE", "test-passphrase")
    @patch("polymarket.auth.POLY_API_SECRET", "dGVzdHNlY3JldDEyMzQ1Ng==")
    def test_headers_use_correct_values(self):
        """Test that headers contain correct credential values."""
        headers = get_l2_headers("GET", "/order/abc")

        self.assertEqual(headers["POLY_ADDRESS"], "0xTestAddress")
        self.assertEqual(headers["POLY_API_KEY"], "test-api-key")
        self.assertEqual(headers["POLY_PASSPHRASE"], "test-passphrase")
        self.assertEqual(headers["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
