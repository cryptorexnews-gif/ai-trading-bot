import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class Notifier:
    """
    Invia notifiche via Telegram.
    Supporta avvisi trade, trigger SL/TP/trailing, errori, e riepiloghi giornalieri.
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
            logger.info("Notifiche Telegram abilitate")
        else:
            logger.info("Telegram non configurato — notifiche disabilitate")

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
            logger.warning(f"Invio Telegram fallito: status={response.status_code}")
            return False
        except Exception as e:
            logger.warning(f"Errore invio Telegram: {e}")
            return False

    def _send(self, message: str, force: bool = False) -> None:
        if not self.enabled:
            return
        if not force and not self._rate_limit_ok():
            return
        self._send_telegram(message)

    def notify_trade(self, trade: Dict[str, Any]) -> None:
        """Invia notifica per trade eseguito."""
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
            f"📏 Dimensione: {size} | 💵 Prezzo: ${price}\n"
            f"💰 Notionale: ${notional}\n"
            f"🎯 Confidenza: {float(confidence)*100:.0f}% | Modalità: {mode}\n"
            f"⚡ Trigger: {trigger}"
        )

        reasoning = trade.get("reasoning", "")
        if reasoning:
            message += f"\n\n💭 <i>{reasoning[:200]}</i>"

        self._send(message)

    def notify_stop_loss(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        pnl_pct = ((current_price - entry_price) / entry_price * Decimal("100")) if entry_price > 0 else Decimal("0")
        message = (
            f"🛑 <b>STOP-LOSS ATTIVATO</b>\n\n"
            f"Coin: <b>{coin}</b>\n"
            f"Entrata: ${entry_price} → Corrente: ${current_price}\n"
            f"Livello Stop: ${trigger_price}\n"
            f"PnL: {float(pnl_pct):.2f}%"
        )
        self._send(message, force=True)

    def notify_take_profit(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        pnl_pct = ((current_price - entry_price) / entry_price * Decimal("100")) if entry_price > 0 else Decimal("0")
        message = (
            f"🎯 <b>TAKE-PROFIT ATTIVATO</b>\n\n"
            f"Coin: <b>{coin}</b>\n"
            f"Entrata: ${entry_price} → Corrente: ${current_price}\n"
            f"TP Livello: ${trigger_price}\n"
            f"PnL: +{float(pnl_pct):.2f}%"
        )
        self._send(message, force=True)

    def notify_trailing_stop(self, coin: str, entry_price: Decimal, trigger_price: Decimal, current_price: Decimal) -> None:
        pnl_pct = ((current_price - entry_price) / entry_price * Decimal("100")) if entry_price > 0 else Decimal("0")
        message = (
            f"📈 <b>TRAILING STOP ATTIVATO</b>\n\n"
            f"Coin: <b>{coin}</b>\n"
            f"Entrata: ${entry_price} → Corrente: ${current_price}\n"
            f"Trailing Stop: ${trigger_price}\n"
            f"PnL: {float(pnl_pct):.2f}%"
        )
        self._send(message, force=True)

    def notify_error(self, error_message: str) -> None:
        message = f"🚨 <b>ERRORE BOT</b>\n\n{error_message[:500]}"
        self._send(message, force=True)

    def notify_emergency_derisk(self, coin: str, reason: str) -> None:
        message = (
            f"🚨🚨 <b>DE-RISK DI EMERGENZA</b>\n\n"
            f"Chiusura: <b>{coin}</b>\n"
            f"Ragione: {reason}"
        )
        self._send(message, force=True)

    def notify_daily_summary(self, summary: Dict[str, Any]) -> None:
        total_trades = summary.get("total_trades", 0)
        win_rate = summary.get("win_rate", 0)
        balance = summary.get("balance", 0)
        pnl = summary.get("daily_pnl", 0)

        pnl_emoji = "📈" if float(str(pnl)) >= 0 else "📉"

        message = (
            f"📊 <b>RIEPILOGO GIORNALIERO</b>\n\n"
            f"💰 Saldo: ${balance}\n"
            f"{pnl_emoji} PnL Giornaliero: ${pnl}\n"
            f"📋 Trade: {total_trades} | Tasso Vittoria: {win_rate:.1f}%\n"
            f"✅ Vittorie: {summary.get('wins', 0)} | ❌ Perdite: {summary.get('losses', 0)}\n"
            f"🔄 Hold: {summary.get('holds', 0)}"
        )
        self._send(message, force=True)

    def notify_bot_started(self, mode: str, pairs: List[str]) -> None:
        message = (
            f"🟢 <b>BOT AVVIATO</b>\n\n"
            f"Modalità: <b>{mode.upper()}</b>\n"
            f"Coppie: {', '.join(pairs)}\n"
            f"Strategia: R:R Asimmetrico (SL 2% / TP 6% / Trailing 1.5%)"
        )
        self._send(message, force=True)

    def notify_bot_stopped(self, reason: str = "manuale") -> None:
        message = f"🔴 <b>BOT FERMO</b>\n\nRagione: {reason}"
        self._send(message, force=True)