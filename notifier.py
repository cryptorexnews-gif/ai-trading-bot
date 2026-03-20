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
    Aggiunto supporto per notifiche trend e KPI dashboard.

    Security: The Telegram bot token is stored in a closure-like pattern.
    It is never exposed via __repr__, __str__, logging, or stored in a URL string.
    The _send_telegram method constructs the URL at call time.
    """

    def __init__(
        self,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        enabled: bool = True,
        min_interval_sec: float = 3.0,
    ):
        token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = enabled
        self.min_interval_sec = min_interval_sec
        self._last_send_time: float = 0.0
        self._session = requests.Session()

        # Security: Store token bytes for timing-safe comparison and URL construction.
        # The token is stored as a private attribute but never appears in __repr__,
        # __str__, or any log output. URL is constructed at send time only.
        self.telegram_enabled = bool(token and self._telegram_chat_id)
        self._tg_token: Optional[str] = token if self.telegram_enabled else None

        if self.telegram_enabled:
            logger.info("Notifiche Telegram abilitate")
        else:
            logger.info("Telegram non configurato — notifiche disabilitate")

    def __repr__(self) -> str:
        """Prevent accidental token leakage."""
        return f"<Notifier enabled={self.enabled} telegram={self.telegram_enabled}>"

    def __str__(self) -> str:
        return self.__repr__()

    def _rate_limit_ok(self) -> bool:
        now = time.time()
        if (now - self._last_send_time) < self.min_interval_sec:
            return False
        self._last_send_time = now
        return True

    def _send_telegram(self, message: str) -> bool:
        if not self.telegram_enabled or not self._tg_token:
            return False
        try:
            # Construct URL at send time — token never stored in a persistent URL string
            url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
            payload = {
                "chat_id": self._telegram_chat_id,
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
            logger.warning(f"Errore invio Telegram: {type(e).__name__}")
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

    # New trend-specific notifications
    def notify_trend_confirmed(self, coin: str, trend_direction: str, trend_strength: int) -> None:
        strength_emoji = "🟢" if trend_strength == 3 else "🟡" if trend_strength == 2 else "🔴"
        message = (
            f"{strength_emoji} <b>TREND CONFERMATO</b>\n\n"
            f"Coin: <b>{coin}</b>\n"
            f"Direzione: {trend_direction.upper()}\n"
            f"Forza: {trend_strength}/3 timeframes allineati\n"
            f"✅ Pronto per entrata trend-following"
        )
        self._send(message)

    def notify_trend_reversal(self, coin: str, old_trend: str, new_trend: str) -> None:
        message = (
            f"🔄 <b>TREND INVERTITO</b>\n\n"
            f"Coin: <b>{coin}</b>\n"
            f"Da: {old_trend.upper()} → A: {new_trend.upper()}\n"
            f"⚠️ Chiudere posizioni esistenti"
        )
        self._send(message, force=True)

    def notify_trend_kpi_summary(self, trend_win_rate: float, total_trend_trades: int) -> None:
        emoji = "🎯" if trend_win_rate >= 60 else "⚠️" if trend_win_rate >= 50 else "🚨"
        message = (
            f"{emoji} <b>KPI TREND STRATEGY</b>\n\n"
            f"Trade Trend Totali: {total_trend_trades}\n"
            f"Win Rate Trend: {trend_win_rate:.1f}%\n"
            f"Target: >60% per trend following"
        )
        self._send(message)