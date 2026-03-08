"""Tests for the dual-leg auto trader."""

import unittest
from unittest.mock import patch, MagicMock
import os
import json
import tempfile


# Patch env vars before importing auto_trader
os.environ["DRY_RUN"] = "True"
os.environ["MIN_MARGIN"] = "0.02"
os.environ["MAX_TOTAL_COST"] = "0.98"

from auto_trader import (
    execute_trade,
    check_balances,
    _has_sufficient_funds,
    _log_trade,
    run_arbitrage_check,
)


def _make_opportunity(
    margin=0.05,
    poly_cost=0.45,
    kalshi_cost=0.50,
    poly_leg="Down",
    kalshi_leg="Yes",
    poly_token_id="tok_down_123",
    kalshi_ticker="KXBTCD-250308-14-89000",
    kalshi_strike=89000.0,
):
    return {
        "type": "Poly > Kalshi",
        "poly_leg": poly_leg,
        "kalshi_leg": kalshi_leg,
        "poly_cost": poly_cost,
        "kalshi_cost": kalshi_cost,
        "total_cost": poly_cost + kalshi_cost,
        "margin": margin,
        "is_arbitrage": True,
        "poly_token_id": poly_token_id,
        "kalshi_strike": kalshi_strike,
        "kalshi_market": {
            "ticker": kalshi_ticker,
            "strike": kalshi_strike,
            "yes_ask": int(kalshi_cost * 100),
            "no_ask": int((1 - kalshi_cost) * 100),
            "yes_bid": int(kalshi_cost * 100) - 2,
            "no_bid": int((1 - kalshi_cost) * 100) - 2,
            "subtitle": f"${kalshi_strike:,.0f} or above",
        },
    }


class TestExecuteTrade(unittest.TestCase):
    """Test dual-leg trade execution."""

    @patch("auto_trader._log_trade")
    @patch("auto_trader.poly_place_order")
    @patch("auto_trader.kalshi_place_order")
    def test_dry_run_both_legs(self, mock_kalshi, mock_poly, mock_log):
        """Both legs succeed in dry run mode."""
        mock_kalshi.return_value = {
            "success": True,
            "order_id": "SIMULATED_K1",
            "error": None,
        }
        mock_poly.return_value = {
            "success": True,
            "order_id": "SIMULATED_P1",
            "error": None,
        }

        opp = _make_opportunity()
        result = execute_trade(opp)

        self.assertEqual(result["status"], "dry_run")
        mock_kalshi.assert_called_once()
        mock_poly.assert_called_once()

        # Verify Kalshi was called with correct args
        k_call = mock_kalshi.call_args
        self.assertEqual(k_call.kwargs["side"], "yes")
        self.assertEqual(k_call.kwargs["action"], "buy")
        self.assertTrue(k_call.kwargs["dry_run"])

        # Verify Poly was called with correct args
        p_call = mock_poly.call_args
        self.assertEqual(p_call.kwargs["side"], "BUY")
        self.assertEqual(p_call.kwargs["token_id"], "tok_down_123")
        self.assertTrue(p_call.kwargs["dry_run"])

    @patch("auto_trader._log_trade")
    @patch("auto_trader.poly_place_order")
    @patch("auto_trader.kalshi_place_order")
    def test_kalshi_failure_no_poly_order(self, mock_kalshi, mock_poly, mock_log):
        """If Kalshi fails, Poly order should NOT be placed."""
        mock_kalshi.return_value = {
            "success": False,
            "order_id": None,
            "error": "Insufficient balance",
        }

        opp = _make_opportunity()
        result = execute_trade(opp)

        self.assertEqual(result["status"], "failed_kalshi")
        mock_poly.assert_not_called()

    @patch("auto_trader._log_trade")
    @patch("auto_trader.kalshi_cancel_order")
    @patch("auto_trader.poly_place_order")
    @patch("auto_trader.kalshi_place_order")
    def test_poly_failure_rolls_back_kalshi(
        self, mock_kalshi, mock_poly, mock_cancel, mock_log
    ):
        """If Poly fails after Kalshi succeeds, Kalshi order is cancelled."""
        mock_kalshi.return_value = {
            "success": True,
            "order_id": "K_ORDER_123",
            "error": None,
        }
        mock_poly.return_value = {
            "success": False,
            "order_id": None,
            "error": "SDK not installed",
        }
        mock_cancel.return_value = {"success": True, "error": None}

        opp = _make_opportunity()
        result = execute_trade(opp)

        self.assertEqual(result["status"], "failed_poly_rollback")
        mock_cancel.assert_called_once_with("K_ORDER_123", dry_run=True)

    @patch("auto_trader._log_trade")
    def test_slippage_rejection(self, mock_log):
        """Trades above MAX_TOTAL_COST are rejected."""
        opp = _make_opportunity(poly_cost=0.55, kalshi_cost=0.46, margin=-0.01)
        opp["total_cost"] = 1.01  # Over the 0.98 threshold
        result = execute_trade(opp)

        self.assertEqual(result["status"], "rejected_slippage")

    @patch("auto_trader._log_trade")
    def test_missing_token_id(self, mock_log):
        """Trade fails if poly_token_id is missing."""
        opp = _make_opportunity(poly_token_id=None)
        result = execute_trade(opp)

        self.assertEqual(result["status"], "failed")
        self.assertIn("token_id", result["error"])

    @patch("auto_trader._log_trade")
    @patch("auto_trader.poly_place_order")
    @patch("auto_trader.kalshi_place_order")
    def test_no_leg_uses_correct_side(self, mock_kalshi, mock_poly, mock_log):
        """When kalshi_leg is No, side should be 'no'."""
        mock_kalshi.return_value = {
            "success": True,
            "order_id": "SIM_K",
            "error": None,
        }
        mock_poly.return_value = {
            "success": True,
            "order_id": "SIM_P",
            "error": None,
        }

        opp = _make_opportunity(kalshi_leg="No", poly_leg="Up")
        execute_trade(opp)

        k_call = mock_kalshi.call_args
        self.assertEqual(k_call.kwargs["side"], "no")


class TestBalanceChecks(unittest.TestCase):
    """Test balance pre-flight checks."""

    @patch("auto_trader.poly_get_balance")
    @patch("auto_trader.kalshi_get_balance")
    def test_check_balances_success(self, mock_kalshi_bal, mock_poly_bal):
        """Successful balance fetch from both platforms."""
        mock_kalshi_bal.return_value = {
            "success": True,
            "data": {"balance": 5000},
            "error": None,
        }
        mock_poly_bal.return_value = {
            "success": True,
            "data": {"balance": "50000000"},  # 50 USDC in raw units
            "error": None,
        }

        result = check_balances()

        self.assertEqual(result["kalshi_balance_cents"], 5000)
        self.assertEqual(result["poly_balance_usdc"], 50.0)
        self.assertEqual(len(result["errors"]), 0)

    @patch("auto_trader.poly_get_balance")
    @patch("auto_trader.kalshi_get_balance")
    def test_check_balances_errors(self, mock_kalshi_bal, mock_poly_bal):
        """Handles balance fetch errors gracefully."""
        mock_kalshi_bal.return_value = {
            "success": False,
            "data": None,
            "error": "Auth failed",
        }
        mock_poly_bal.return_value = {
            "success": False,
            "data": None,
            "error": "SDK missing",
        }

        result = check_balances()

        self.assertIsNone(result["kalshi_balance_cents"])
        self.assertIsNone(result["poly_balance_usdc"])
        self.assertEqual(len(result["errors"]), 2)

    def test_has_sufficient_funds(self):
        """Sufficient funds check passes."""
        balances = {
            "kalshi_balance_cents": 10000,
            "poly_balance_usdc": 100.0,
            "errors": [],
        }
        opp = _make_opportunity(kalshi_cost=0.50, poly_cost=0.45)

        ok, reason = _has_sufficient_funds(balances, opp)
        self.assertTrue(ok)

    def test_insufficient_kalshi_funds(self):
        """Kalshi balance too low."""
        balances = {
            "kalshi_balance_cents": 10,  # Only 10 cents
            "poly_balance_usdc": 100.0,
            "errors": [],
        }
        opp = _make_opportunity(kalshi_cost=0.50)

        ok, reason = _has_sufficient_funds(balances, opp)
        self.assertFalse(ok)
        self.assertIn("Kalshi", reason)

    def test_insufficient_poly_funds(self):
        """Poly balance too low."""
        balances = {
            "kalshi_balance_cents": 10000,
            "poly_balance_usdc": 0.01,  # Almost nothing
            "errors": [],
        }
        opp = _make_opportunity(poly_cost=0.45)

        ok, reason = _has_sufficient_funds(balances, opp)
        self.assertFalse(ok)
        self.assertIn("Poly", reason)

    def test_none_balance_skips_check(self):
        """If balance is None (fetch failed), don't block the trade."""
        balances = {
            "kalshi_balance_cents": None,
            "poly_balance_usdc": None,
            "errors": ["fetch failed"],
        }
        opp = _make_opportunity()

        ok, reason = _has_sufficient_funds(balances, opp)
        self.assertTrue(ok)


class TestTradeLog(unittest.TestCase):
    """Test trade history logging."""

    def test_log_trade_creates_file(self):
        """First trade creates the log file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmpfile = f.name

        # Remove the file so _log_trade creates it
        os.unlink(tmpfile)

        # Temporarily override the log file path
        import auto_trader

        original = auto_trader.TRADE_LOG_FILE
        auto_trader.TRADE_LOG_FILE = tmpfile

        try:
            _log_trade({"status": "test", "margin": 0.05})

            with open(tmpfile) as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["status"], "test")
        finally:
            auto_trader.TRADE_LOG_FILE = original
            if os.path.exists(tmpfile):
                os.unlink(tmpfile)

    def test_log_trade_appends(self):
        """Subsequent trades append to log."""
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            json.dump([{"status": "first"}], f)
            tmpfile = f.name

        import auto_trader

        original = auto_trader.TRADE_LOG_FILE
        auto_trader.TRADE_LOG_FILE = tmpfile

        try:
            _log_trade({"status": "second"})

            with open(tmpfile) as f:
                data = json.load(f)
            self.assertEqual(len(data), 2)
        finally:
            auto_trader.TRADE_LOG_FILE = original
            os.unlink(tmpfile)


class TestRunArbitrageCheck(unittest.TestCase):
    """Test the main arbitrage check cycle."""

    @patch("auto_trader.check_balances")
    @patch("auto_trader.find_opportunities")
    @patch("auto_trader.fetch_kalshi_data_struct")
    @patch("auto_trader.fetch_polymarket_data_struct")
    def test_no_opportunities(self, mock_poly, mock_kalshi, mock_find, mock_bal):
        """No trades when no opportunities exist."""
        mock_poly.return_value = ({"prices": {}, "token_ids": {}}, None)
        mock_kalshi.return_value = ({"markets": []}, None)
        mock_find.return_value = ([], [])

        result = run_arbitrage_check()

        self.assertEqual(len(result["executed_trades"]), 0)
        self.assertEqual(len(result["opportunities"]), 0)

    @patch("auto_trader.execute_trade")
    @patch("auto_trader.check_balances")
    @patch("auto_trader.find_opportunities")
    @patch("auto_trader.fetch_kalshi_data_struct")
    @patch("auto_trader.fetch_polymarket_data_struct")
    def test_executes_qualifying_trades(
        self, mock_poly, mock_kalshi, mock_find, mock_bal, mock_exec
    ):
        """Trades are executed when margin meets threshold."""
        mock_poly.return_value = (
            {"prices": {"Up": 0.4, "Down": 0.3}, "token_ids": {"Up": "t1", "Down": "t2"}},
            None,
        )
        mock_kalshi.return_value = ({"markets": []}, None)

        good_opp = _make_opportunity(margin=0.05)
        bad_opp = _make_opportunity(margin=0.01)  # Below MIN_MARGIN
        mock_find.return_value = ([good_opp, bad_opp], [])

        mock_bal.return_value = {
            "kalshi_balance_cents": 10000,
            "poly_balance_usdc": 100.0,
            "errors": [],
        }
        mock_exec.return_value = {"status": "dry_run"}

        result = run_arbitrage_check()

        # Only the good opportunity should be executed
        self.assertEqual(mock_exec.call_count, 1)
        self.assertEqual(len(result["executed_trades"]), 1)

    @patch("auto_trader.find_opportunities")
    @patch("auto_trader.fetch_kalshi_data_struct")
    @patch("auto_trader.fetch_polymarket_data_struct")
    def test_handles_fetch_errors(self, mock_poly, mock_kalshi, mock_find):
        """Errors in data fetching are captured."""
        mock_poly.return_value = (None, "API timeout")
        mock_kalshi.return_value = (None, "Auth failed")

        result = run_arbitrage_check()

        self.assertEqual(len(result["errors"]), 2)
        self.assertEqual(len(result["executed_trades"]), 0)
        mock_find.assert_not_called()


if __name__ == "__main__":
    unittest.main()
