import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class Notifier:
    """
    Send notifications via Telegram and/or Discord.
    Supports trade alerts, error alerts, and daily summaries.
    """

    def __init__(
        self,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        discord_webhook_url: Optional[str] = None,
        enabled: bool = True,
        min_interval_sec: float = 5.0,
    ):
        self.telegram_bot_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.discord_webhook_url = discord_webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.enabled = enabled
        self.min_interval_sec = min_interval_sec
        self._last_send_time: float = 0.0
        self._session = requests.Session()

        self.telegram_enabled = bool(self.telegram_bot_token and self.telegram_chat_id)
        self.discord_enabled = bool(self.discord_webhook_url)

        if self.telegram_enabled:
            logger.info("Telegram notifications enabled")
        if self.discord_enabled:
            logger.info("Discord notifications enabled")
        if not self.telegram_enabled and not self.discord_enabled:
            logger.info("No notification channels configured")

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

    def _send_discord(self, message: str) -> bool:
        if not self.discord_enabled:
            return False
        try:
            payload = {"content": message}
            response = self._session.post(
                self.discord_webhook_url, json=payload, timeout=10
            )
            if response.status_code in (200, 204):
                return True
            logger.warning(f"Discord send failed: status={response.status_code}")
            return False
        except Exception as e:
            logger.warning(f"Discord send error: {e}")
            return False

    def _send(self, message: str, force: bool = False) -> None:
        if not self.enabled:
            return
        if not force and not self._rate_limit_ok():
            return
        self._send_telegram(message)
        self._send_discord(message)

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

        trigger_emoji = {
            "ai": "🤖",
            "stop_loss": "🛑",
            "take_profit": "🎯",
            "trailing_stop": "📈",
            "emergency": "🚨",
        }.get(trigger, "📊")

        message = (
            f"{success} {trigger_emoji} <b>{action}</b> {coin}\n"
            f"Size: {size} | Price: ${price}\n"
            f"Confidence: {float(confidence)*100:.0f}% | Mode: {mode}\n"
            f"Trigger: {trigger}"
        )

        reasoning = trade.get("reasoning", "")
        if reasoning:
            message += f"\n<i>{reasoning[:150]}</i>"

        self._send(message)

    def notify_stop_loss(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        message = (
            f"🛑 <b>STOP-LOSS TRIGGERED</b>\n"
            f"Coin: {coin}\n"
            f"Entry: ${entry_price} → Current: ${current_price}\n"
            f"Stop Level: ${trigger_price}"
        )
        self._send(message, force=True)

    def notify_take_profit(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        message = (
            f"🎯 <b>TAKE-PROFIT TRIGGERED</b>\n"
            f"Coin: {coin}\n"
            f"Entry: ${entry_price} → Current: ${current_price}\n"
            f"TP Level: ${trigger_price}"
        )
        self._send(message, force=True)

    def notify_trailing_stop(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        message = (
            f"📈 <b>TRAILING STOP TRIGGERED</b>\n"
            f"Coin: {coin}\n"
            f"Entry: ${entry_price} → Current: ${current_price}\n"
            f"Trailing Stop: ${trigger_price}"
        )
        self._send(message, force=True)

    def notify_error(self, error_message: str) -> None:
        message = f"🚨 <b>BOT ERROR</b>\n{error_message[:500]}"
        self._send(message, force=True)

    def notify_emergency_derisk(self, coin: str, reason: str) -> None:
        message = (
            f"🚨🚨 <b>EMERGENCY DE-RISK</b>\n"
            f"Closing {coin}\n"
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
            f"📊 <b>DAILY SUMMARY</b>\n"
            f"Balance: ${balance}\n"
            f"{pnl_emoji} Daily PnL: ${pnl}\n"
            f"Trades: {total_trades} | Win Rate: {win_rate:.1f}%\n"
            f"Wins: {summary.get('wins', 0)} | Losses: {summary.get('losses', 0)}"
        )
        self._send(message, force=True)

    def notify_bot_started(self, mode: str, pairs: List[str]) -> None:
        message = (
            f"🟢 <b>BOT STARTED</b>\n"
            f"Mode: {mode.upper()}\n"
            f"Pairs: {', '.join(pairs)}"
        )
        self._send(message, force=True)

    def notify_bot_stopped(self, reason: str = "manual") -> None:
        message = f"🔴 <b>BOT STOPPED</b>\nReason: {reason}"
        self._send(message, force=True)