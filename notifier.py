import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class Notifier:
    """
    Send notifications via Telegram.
    Supports trade alerts, SL/TP/trailing triggers, errors, and daily summaries.
    """

    def __init__(
        self,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        enabled: bool = True,
        min_interval_sec: float = 3.0,
    ):
        self.telegram_bot_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = enabled
        self.min_interval_sec = min_interval_sec
        self._last_send_time: float = 0.0
        self._session = requests.Session()

        self.telegram_enabled = bool(self.telegram_bot_token and self.telegram_chat_id)

        if self.telegram_enabled:
            logger.info("Telegram notifications enabled")
        else:
            logger.info("Telegram not configured — notifications disabled")

    def _rate_limit_ok(self) -> bool:
        now = time.time()
        if (now - self._last_send_time) < self.min_interval_sec:
            return False
        self._last_send_time = now
        return True

    def _send_telegram(self, message: str) -> bool:
        if not self.telegram_enabled:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            response = self._session.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            logger.warning(f"Telegram send failed: status={response.status_code}")
            return False
        except Exception as e:
            logger.warning(f"Telegram send error: {e}")
            return False

    def _send(self, message: str, force: bool = False) -> None:
        if not self.enabled:
            return
        if not force and not self._rate_limit_ok():
            return
        self._send_telegram(message)

    def notify_trade(self, trade: Dict[str, Any]) -> None:
        """Send notification for an executed trade."""
        action = trade.get("action", "unknown").upper()
        coin = trade.get("coin", "?")
        size = trade.get("size", "?")
        price = trade.get("price", "?")
        confidence = trade.get("confidence", 0)
        mode = trade.get("mode", "paper").upper()
        success = "✅" if trade.get("success") else "❌"
        trigger = trade.get("trigger", "ai")
        notional = trade.get("notional", "0")

        trigger_emoji = {
            "ai": "🤖",
            "stop_loss": "🛑",
            "take_profit": "🎯",
            "trailing_stop": "📈",
            "emergency": "🚨",
        }.get(trigger, "📊")

        message = (
            f"{success} {trigger_emoji} <b>{action}</b> {coin}\n"
            f"📏 Size: {size} | 💵 Price: ${price}\n"
            f"💰 Notional: ${notional}\n"
            f"🎯 Confidence: {float(confidence)*100:.0f}% | Mode: {mode}\n"
            f"⚡ Trigger: {trigger}"
        )

        reasoning = trade.get("reasoning", "")
        if reasoning:
            message += f"\n\n💭 <i>{reasoning[:200]}</i>"

        self._send(message)

    def notify_stop_loss(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        pnl_pct = ((current_price - entry_price) / entry_price * Decimal("100")) if entry_price > 0 else Decimal("0")
        message = (
            f"🛑 <b>STOP-LOSS TRIGGERED</b>\n\n"
            f"Coin: <b>{coin}</b>\n"
            f"Entry: ${entry_price} → Current: ${current_price}\n"
            f"Stop Level: ${trigger_price}\n"
            f"PnL: {float(pnl_pct):.2f}%"
        )
        self._send(message, force=True)

    def notify_take_profit(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        pnl_pct = ((current_price - entry_price) / entry_price * Decimal("100")) if entry_price > 0 else Decimal("0")
        message = (
            f"🎯 <b>TAKE-PROFIT TRIGGERED</b>\n\n"
            f"Coin: <b>{coin}</b>\n"
            f"Entry: ${entry_price} → Current: ${current_price}\n"
            f"TP Level: ${trigger_price}\n"
            f"PnL: +{float(pnl_pct):.2f}%"
        )
        self._send(message, force=True)

    def notify_trailing_stop(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        pnl_pct = ((current_price - entry_price) / entry_price * Decimal("100")) if entry_price > 0 else Decimal("0")
        message = (
            f"📈 <b>TRAILING STOP TRIGGERED</b>\n\n"
            f"Coin: <b>{coin}</b>\n"
            f"Entry: ${entry_price} → Current: ${current_price}\n"
            f"Trailing Stop: ${trigger_price}\n"
            f"PnL: {float(pnl_pct):.2f}%"
        )
        self._send(message, force=True)

    def notify_error(self, error_message: str) -> None:
        message = f"🚨 <b>BOT ERROR</b>\n\n{error_message[:500]}"
        self._send(message, force=True)

    def notify_emergency_derisk(self, coin: str, reason: str) -> None:
        message = (
            f"🚨🚨 <b>EMERGENCY DE-RISK</b>\n\n"
            f"Closing: <b>{coin}</b>\n"
            f"Reason: {reason}"
        )
        self._send(message, force=True)

    def notify_daily_summary(self, summary: Dict[str, Any]) -> None:
        total_trades = summary.get("total_trades", 0)
        win_rate = summary.get("win_rate", 0)
        balance = summary.get("balance", 0)
        pnl = summary.get("daily_pnl", 0)

        pnl_emoji = "📈" if float(str(pnl)) >= 0 else "📉"

        message = (
            f"📊 <b>DAILY SUMMARY</b>\n\n"
            f"💰 Balance: ${balance}\n"
            f"{pnl_emoji} Daily PnL: ${pnl}\n"
            f"📋 Trades: {total_trades} | Win Rate: {win_rate:.1f}%\n"
            f"✅ Wins: {summary.get('wins', 0)} | ❌ Losses: {summary.get('losses', 0)}\n"
            f"🔄 Holds: {summary.get('holds', 0)}"
        )
        self._send(message, force=True)

    def notify_bot_started(self, mode: str, pairs: List[str]) -> None:
        message = (
            f"🟢 <b>BOT STARTED</b>\n\n"
            f"Mode: <b>{mode.upper()}</b>\n"
            f"Pairs: {', '.join(pairs)}\n"
            f"Strategy: Asymmetric R:R (SL 2% / TP 6% / Trailing 1.5%)"
        )
        self._send(message, force=True)

    def notify_bot_stopped(self, reason: str = "manual") -> None:
        message = f"🔴 <b>BOT STOPPED</b>\n\nReason: {reason}"
        self._send(message, force=True)