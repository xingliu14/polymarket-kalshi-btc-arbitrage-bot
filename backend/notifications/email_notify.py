"""Email notification module for trade alerts and daily summaries.

Uses SMTP (compatible with Gmail app passwords, SendGrid, etc.).

Configuration via environment variables:
- EMAIL_ENABLED: Enable email notifications (default "False")
- SMTP_HOST: SMTP server host (default "smtp.gmail.com")
- SMTP_PORT: SMTP server port (default 587)
- SMTP_USER: SMTP login username (your email)
- SMTP_PASSWORD: SMTP login password (Gmail app password)
- NOTIFY_TO: Recipient email address
- DAILY_SUMMARY_HOUR: Hour (0-23) for daily summary in local time (default 7)
"""

import os
import json
import smtplib
import threading
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "False").lower() in ("true", "1", "yes")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFY_TO = os.getenv("NOTIFY_TO", "")
DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "7"))


def _send_email(subject: str, body_html: str) -> bool:
    """Send an email via SMTP. Returns True on success."""
    if not EMAIL_ENABLED:
        return False
    if not all([SMTP_USER, SMTP_PASSWORD, NOTIFY_TO]):
        print("[EMAIL] Missing SMTP_USER, SMTP_PASSWORD, or NOTIFY_TO config")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_TO
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, NOTIFY_TO, msg.as_string())
        print(f"[EMAIL] Sent: {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed to send: {e}")
        return False


def notify_losing_trade(trade: dict):
    """Send an alert email when a trade results in a loss.

    Args:
        trade: The execution record dict from execute_trade()
    """
    if not EMAIL_ENABLED:
        return

    status = trade.get("status", "unknown")
    opp = trade.get("opportunity", {})
    timestamp = trade.get("timestamp", "N/A")

    if status == "partial_kalshi_only":
        loss_desc = f"Kalshi filled but Polymarket didn't — exposed on Kalshi side"
        loss_amount = opp.get("kalshi_cost", 0)
    elif status == "partial_poly_only":
        loss_desc = f"Polymarket filled but Kalshi didn't — exposed on Polymarket side"
        loss_amount = opp.get("poly_cost", 0)
    else:
        return  # Not a losing trade

    subject = f"[ARBIT BOT] Losing trade: {status}"

    body = f"""
    <h2 style="color: #d32f2f;">Losing Trade Alert</h2>
    <table style="border-collapse: collapse; font-family: monospace;">
        <tr><td style="padding: 4px 12px;"><b>Time</b></td><td>{timestamp}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Status</b></td><td style="color: #d32f2f;">{status}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>What happened</b></td><td>{loss_desc}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Potential loss</b></td><td>${loss_amount:.4f}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Type</b></td><td>{opp.get('type', 'N/A')}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Kalshi strike</b></td><td>${opp.get('kalshi_strike', 0):,.0f}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Poly leg</b></td><td>{opp.get('poly_leg', 'N/A')} @ ${opp.get('poly_cost', 0):.4f}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Kalshi leg</b></td><td>{opp.get('kalshi_leg', 'N/A')} @ ${opp.get('kalshi_cost', 0):.4f}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Margin</b></td><td>{opp.get('margin', 0):.4f}</td></tr>
    </table>
    <p style="color: #888; font-size: 12px;">Automated alert from BTC Arbitrage Bot</p>
    """

    _send_email(subject, body)


def build_daily_summary(trade_log_file: str, contracts_per_trade: int, poly_size_per_trade: float) -> str | None:
    """Build HTML summary of the last 24 hours of trading.

    Returns HTML body string, or None if no trades to report.
    """
    if not os.path.exists(trade_log_file):
        return None

    try:
        with open(trade_log_file, "r") as f:
            history = json.load(f)
    except Exception:
        return None

    # Filter trades from last 24 hours
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    recent = []
    for trade in history:
        ts_str = trade.get("timestamp", "")
        try:
            ts = datetime.datetime.fromisoformat(ts_str)
            if ts >= cutoff:
                recent.append(trade)
        except (ValueError, TypeError):
            continue

    # Compute stats
    total_pnl = 0.0
    wins = 0
    losses = 0
    total_trades = 0

    trade_rows = []
    for trade in recent:
        status = trade.get("status", "")
        opp = trade.get("opportunity", {})
        margin = opp.get("margin", 0)
        poly_cost = opp.get("poly_cost", 0)
        kalshi_cost = opp.get("kalshi_cost", 0)

        pnl = 0.0
        if status in ("filled", "dry_run"):
            pnl = margin * contracts_per_trade
            wins += 1
            total_trades += 1
        elif status == "partial_kalshi_only":
            pnl = -(kalshi_cost * contracts_per_trade)
            losses += 1
            total_trades += 1
        elif status == "partial_poly_only":
            pnl = -(poly_cost * poly_size_per_trade)
            losses += 1
            total_trades += 1

        total_pnl += pnl

        color = "#4caf50" if pnl > 0 else "#d32f2f" if pnl < 0 else "#888"
        trade_rows.append(
            f"<tr>"
            f"<td style='padding: 4px 8px;'>{trade.get('timestamp', 'N/A')[:19]}</td>"
            f"<td style='padding: 4px 8px;'>{status}</td>"
            f"<td style='padding: 4px 8px;'>{opp.get('type', 'N/A')}</td>"
            f"<td style='padding: 4px 8px;'>${opp.get('kalshi_strike', 0):,.0f}</td>"
            f"<td style='padding: 4px 8px; color: {color};'>${pnl:+.4f}</td>"
            f"</tr>"
        )

    pnl_color = "#4caf50" if total_pnl > 0 else "#d32f2f" if total_pnl < 0 else "#888"

    trades_table = ""
    if trade_rows:
        trades_table = f"""
        <table style="border-collapse: collapse; font-family: monospace; width: 100%;">
            <tr style="background: #f5f5f5;">
                <th style="padding: 4px 8px; text-align: left;">Time</th>
                <th style="padding: 4px 8px; text-align: left;">Status</th>
                <th style="padding: 4px 8px; text-align: left;">Type</th>
                <th style="padding: 4px 8px; text-align: left;">Strike</th>
                <th style="padding: 4px 8px; text-align: left;">P&L</th>
            </tr>
            {''.join(trade_rows)}
        </table>
        """

    body = f"""
    <h2>Daily Trading Summary</h2>
    <p>Last 24 hours as of {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
    <table style="border-collapse: collapse; font-family: monospace;">
        <tr><td style="padding: 4px 12px;"><b>Total trades</b></td><td>{total_trades}</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Wins / Losses</b></td><td>{wins}W / {losses}L</td></tr>
        <tr><td style="padding: 4px 12px;"><b>Net P&L</b></td>
            <td style="color: {pnl_color}; font-weight: bold;">${total_pnl:+.4f}</td></tr>
    </table>
    {trades_table if trade_rows else '<p style="color: #888;">No trades in the last 24 hours.</p>'}
    <p style="color: #888; font-size: 12px;">Automated summary from BTC Arbitrage Bot</p>
    """

    return body


def send_daily_summary(trade_log_file: str, contracts_per_trade: int, poly_size_per_trade: float):
    """Build and send the daily trading summary email."""
    body = build_daily_summary(trade_log_file, contracts_per_trade, poly_size_per_trade)
    if body is None:
        print("[EMAIL] No trade log found — skipping daily summary")
        return
    _send_email("[ARBIT BOT] Daily Trading Summary", body)


class DailySummaryScheduler:
    """Background thread that sends a daily summary email at a configured hour.

    Checks every 60 seconds if it's time to send. Sends once per calendar day.
    """

    def __init__(self, trade_log_file: str, contracts_per_trade: int, poly_size_per_trade: float):
        self._trade_log_file = trade_log_file
        self._contracts = contracts_per_trade
        self._poly_size = poly_size_per_trade
        self._last_sent_date = None
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if not EMAIL_ENABLED:
            print("[EMAIL] Notifications disabled — daily summary scheduler not started")
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[EMAIL] Daily summary scheduler started (sends at {DAILY_SUMMARY_HOUR:02d}:00 local time)")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._stop_event.is_set():
            now = datetime.datetime.now()
            today = now.date()

            if now.hour == DAILY_SUMMARY_HOUR and self._last_sent_date != today:
                send_daily_summary(self._trade_log_file, self._contracts, self._poly_size)
                self._last_sent_date = today

            self._stop_event.wait(60)
