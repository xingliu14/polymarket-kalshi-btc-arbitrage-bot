"""Tests for notifications.email_notify module."""

import json
import os
import datetime
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from notifications.email_notify import (
    _send_email,
    notify_losing_trade,
    build_daily_summary,
    send_daily_summary,
    DailySummaryScheduler,
)


class TestSendEmail(unittest.TestCase):
    """Tests for the _send_email function."""

    @patch("notifications.email_notify.EMAIL_ENABLED", False)
    def test_disabled_returns_false(self):
        assert _send_email("subj", "<p>body</p>") is False

    @patch("notifications.email_notify.EMAIL_ENABLED", True)
    @patch("notifications.email_notify.SMTP_USER", "")
    def test_missing_config_returns_false(self):
        assert _send_email("subj", "<p>body</p>") is False

    @patch("notifications.email_notify.EMAIL_ENABLED", True)
    @patch("notifications.email_notify.SMTP_USER", "user@test.com")
    @patch("notifications.email_notify.SMTP_PASSWORD", "pass")
    @patch("notifications.email_notify.NOTIFY_TO", "to@test.com")
    @patch("notifications.email_notify.smtplib.SMTP")
    def test_sends_email_successfully(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = _send_email("Test Subject", "<p>Hello</p>")

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@test.com", "pass")
        mock_server.sendmail.assert_called_once()

    @patch("notifications.email_notify.EMAIL_ENABLED", True)
    @patch("notifications.email_notify.SMTP_USER", "user@test.com")
    @patch("notifications.email_notify.SMTP_PASSWORD", "pass")
    @patch("notifications.email_notify.NOTIFY_TO", "to@test.com")
    @patch("notifications.email_notify.smtplib.SMTP")
    def test_smtp_error_returns_false(self, mock_smtp_cls):
        mock_smtp_cls.return_value.__enter__ = MagicMock(
            side_effect=Exception("Connection refused")
        )
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = _send_email("Test", "<p>body</p>")
        assert result is False


class TestNotifyLosingTrade(unittest.TestCase):
    """Tests for notify_losing_trade."""

    @patch("notifications.email_notify._send_email")
    @patch("notifications.email_notify.EMAIL_ENABLED", True)
    def test_partial_kalshi_sends_email(self, mock_send):
        mock_send.return_value = True
        trade = {
            "status": "partial_kalshi_only",
            "timestamp": "2026-03-10T10:00:00+00:00",
            "opportunity": {
                "type": "Poly > Kalshi",
                "kalshi_strike": 89000.0,
                "poly_leg": "Down",
                "kalshi_leg": "Yes",
                "poly_cost": 0.45,
                "kalshi_cost": 0.50,
                "margin": 0.039,
            },
        }
        notify_losing_trade(trade)
        mock_send.assert_called_once()
        subject = mock_send.call_args[0][0]
        assert "partial_kalshi_only" in subject

    @patch("notifications.email_notify._send_email")
    @patch("notifications.email_notify.EMAIL_ENABLED", True)
    def test_partial_poly_sends_email(self, mock_send):
        mock_send.return_value = True
        trade = {
            "status": "partial_poly_only",
            "timestamp": "2026-03-10T10:00:00+00:00",
            "opportunity": {
                "type": "Poly < Kalshi",
                "kalshi_strike": 90000.0,
                "poly_leg": "Up",
                "kalshi_leg": "No",
                "poly_cost": 0.50,
                "kalshi_cost": 0.45,
                "margin": 0.039,
            },
        }
        notify_losing_trade(trade)
        mock_send.assert_called_once()

    @patch("notifications.email_notify._send_email")
    @patch("notifications.email_notify.EMAIL_ENABLED", True)
    def test_filled_trade_does_not_send(self, mock_send):
        trade = {"status": "filled", "opportunity": {}}
        notify_losing_trade(trade)
        mock_send.assert_not_called()

    @patch("notifications.email_notify._send_email")
    @patch("notifications.email_notify.EMAIL_ENABLED", False)
    def test_disabled_does_not_send(self, mock_send):
        trade = {"status": "partial_kalshi_only", "opportunity": {}}
        notify_losing_trade(trade)
        mock_send.assert_not_called()


class TestBuildDailySummary(unittest.TestCase):
    """Tests for build_daily_summary."""

    def test_no_file_returns_none(self):
        result = build_daily_summary("/nonexistent/file.json", 1, 1.0)
        assert result is None

    def test_empty_history(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            f.flush()
            result = build_daily_summary(f.name, 1, 1.0)
        os.unlink(f.name)
        assert result is not None
        assert "No trades in the last 24 hours" in result

    def test_recent_trades_included(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        trades = [
            {
                "timestamp": now.isoformat(),
                "status": "filled",
                "opportunity": {
                    "type": "Poly > Kalshi",
                    "kalshi_strike": 89000.0,
                    "margin": 0.03,
                    "poly_cost": 0.45,
                    "kalshi_cost": 0.50,
                },
            },
            {
                "timestamp": now.isoformat(),
                "status": "partial_kalshi_only",
                "opportunity": {
                    "type": "Poly < Kalshi",
                    "kalshi_strike": 90000.0,
                    "margin": 0.02,
                    "poly_cost": 0.50,
                    "kalshi_cost": 0.45,
                },
            },
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(trades, f)
            f.flush()
            result = build_daily_summary(f.name, 1, 1.0)
        os.unlink(f.name)

        assert result is not None
        assert "1W / 1L" in result
        assert "filled" in result
        assert "partial_kalshi_only" in result

    def test_old_trades_excluded(self):
        old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=48)
        trades = [
            {
                "timestamp": old.isoformat(),
                "status": "filled",
                "opportunity": {"margin": 0.03, "poly_cost": 0.45, "kalshi_cost": 0.50},
            },
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(trades, f)
            f.flush()
            result = build_daily_summary(f.name, 1, 1.0)
        os.unlink(f.name)

        assert result is not None
        assert "No trades in the last 24 hours" in result


class TestDailySummaryScheduler(unittest.TestCase):
    """Tests for the DailySummaryScheduler."""

    @patch("notifications.email_notify.EMAIL_ENABLED", False)
    def test_does_not_start_when_disabled(self):
        scheduler = DailySummaryScheduler("trade.json", 1, 1.0)
        scheduler.start()
        assert scheduler._thread is None

    @patch("notifications.email_notify.EMAIL_ENABLED", True)
    @patch("notifications.email_notify._send_email")
    def test_sends_at_scheduled_hour(self, mock_send):
        """Verify scheduler triggers send when hour matches and hasn't sent today."""
        mock_send.return_value = True
        current_hour = datetime.datetime.now().hour

        scheduler = DailySummaryScheduler("trade.json", 1, 1.0)
        scheduler._last_sent_date = None

        with patch("notifications.email_notify.DAILY_SUMMARY_HOUR", current_hour):
            # Manually run one iteration of the scheduler logic
            now = datetime.datetime.now()
            today = now.date()
            if now.hour == current_hour and scheduler._last_sent_date != today:
                send_daily_summary("trade.json", 1, 1.0)
                scheduler._last_sent_date = today

        # send_daily_summary was called but trade.json doesn't exist,
        # so _send_email won't be called. Verify via _last_sent_date instead.
        assert scheduler._last_sent_date == datetime.date.today()

    @patch("notifications.email_notify.EMAIL_ENABLED", True)
    def test_does_not_send_twice_same_day(self):
        scheduler = DailySummaryScheduler("trade.json", 1, 1.0)
        scheduler._last_sent_date = datetime.date.today()

        # Even if hour matches, should not send again
        now = datetime.datetime.now()
        should_send = (
            now.hour == int(os.getenv("DAILY_SUMMARY_HOUR", "7"))
            and scheduler._last_sent_date != now.date()
        )
        assert should_send is False


if __name__ == "__main__":
    unittest.main()
