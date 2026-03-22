import logging
import time
from decimal import Decimal
from typing import Any, Dict, Tuple

from technical_analyzer_simple import technical_fetcher

logger = logging.getLogger(__name__)


class RiskTriggerService:
    """Handles trigger checks (SL/TP/trailing/break-even) and trigger-driven closes."""

    def __init__(
        self,
        cfg,
        hl_rate_limiter,
        exchange_client,
        portfolio_service,
        position_manager,
        notifier,
        metrics,
        state_store,
        protective_orders_service,
    ):
        self.cfg = cfg
        self.hl_rate_limiter = hl_rate_limiter
        self.exchange_client = exchange_client
        self.portfolio_service = portfolio_service
        self.position_manager = position_manager
        self.notifier = notifier
        self.metrics = metrics
        self.state_store = state_store
        self.protective_orders_service = protective_orders_service

        self.trigger_close_max_attempts = 8
        self.trigger_close_base_sleep_sec = 1.0

    def execute_trigger_close_with_retries(
        self,
        coin: str,
        side: str,
        close_size: Decimal,
        current_price: Decimal,
        trigger: str,
        previous_size: Decimal,
    ) -> Tuple[bool, Dict[str, Any]]:
        last_result: Dict[str, Any] = {"success": False, "reason": "not_executed"}

        for attempt in range(1, self.trigger_close_max_attempts + 1):
            self.hl_rate_limiter.acquire(1)
            result = self.exchange_client.place_order(
                coin=coin,
                side=side,
                size=close_size,
                desired_price=current_price,
                reduce_only=True,
            )
            last_result = result if isinstance(result, dict) else {"success": False, "reason": "invalid_result"}

            if not last_result.get("success"):
                logger.warning(
                    f"{trigger.upper()} close attempt {attempt}/{self.trigger_close_max_attempts} failed for {coin}: "
                    f"{last_result.get('reason', 'unknown')}"
                )
                if attempt < self.trigger_close_max_attempts:
                    backoff = self.trigger_close_base_sleep_sec + min(2.0, attempt * 0.2)
                    time.sleep(backoff)
                continue

            refreshed = self.portfolio_service.get_portfolio_state()
            new_size = Decimal(str(refreshed.positions.get(coin, {}).get("size", 0)))

            if abs(new_size) < abs(previous_size):
                logger.info(
                    f"{trigger.upper()} close confirmed on exchange for {coin}: "
                    f"size {previous_size} -> {new_size}"
                )
                return True, last_result

            logger.warning(
                f"{trigger.upper()} close attempt {attempt}/{self.trigger_close_max_attempts} not reflected yet on exchange for {coin} "
                f"(expected reduction from {previous_size}, got {new_size})"
            )
            if attempt < self.trigger_close_max_attempts:
                time.sleep(self.trigger_close_base_sleep_sec)

        return False, last_result

    def _send_trigger_notification(
        self,
        trigger: str,
        coin: str,
        entry_price: Decimal,
        trigger_price: Decimal,
        current_price: Decimal,
    ) -> None:
        if trigger == "stop_loss" or trigger == "break_even_stop":
            self.notifier.notify_stop_loss(coin, entry_price, trigger_price, current_price)
        elif trigger == "take_profit":
            self.notifier.notify_take_profit(coin, entry_price, trigger_price, current_price)
        elif trigger == "trailing_stop":
            self.notifier.notify_trailing_stop(coin, entry_price, trigger_price, current_price)

    def _record_trigger_trade(
        self,
        coin: str,
        close_size: Decimal,
        current_price: Decimal,
        result: Dict[str, Any],
        action_info: Dict[str, Any],
        trigger: str
    ) -> None:
        state = self.state_store.load_state()
        trade_record = {
            "timestamp": time.time(),
            "coin": coin,
            "action": "close_position",
            "size": str(close_size),
            "price": str(current_price),
            "notional": str(result.get("notional", "0")),
            "leverage": 1,
            "confidence": 1.0,
            "reasoning": action_info.get("reasoning", ""),
            "success": True,
            "mode": self.cfg.execution_mode,
            "trigger": trigger,
            "order_status": "filled",
        }
        self.state_store.add_trade_record(state, trade_record)
        self.state_store.save_state(state)

    def process_risk_triggers(self, portfolio) -> int:
        self.position_manager.sync_with_exchange(portfolio.positions)
        self.protective_orders_service.ensure_protective_orders_for_open_positions(portfolio)

        mids = technical_fetcher.get_all_mids()
        if not mids:
            return 0

        current_prices: Dict[str, Decimal] = {}
        for coin in portfolio.positions:
            if coin in mids:
                current_prices[coin] = Decimal(str(mids[coin]))

        actions = self.position_manager.check_all_positions(current_prices)
        triggered = 0

        for action_info in actions:
            coin = action_info["coin"]
            trigger = action_info["trigger"]
            current_price = action_info["current_price"]
            trigger_price = action_info.get("trigger_price", Decimal("0"))
            entry_price = action_info.get("entry_price", Decimal("0"))

            logger.warning(
                f"{trigger.upper()} triggered for {coin}: "
                f"entry=${entry_price}, current=${current_price}, trigger=${trigger_price}"
            )

            pos_size = Decimal(str(portfolio.positions[coin]["size"]))
            side = "sell" if pos_size > 0 else "buy"
            close_size = abs(pos_size)

            close_ok, result = self.execute_trigger_close_with_retries(
                coin=coin,
                side=side,
                close_size=close_size,
                current_price=current_price,
                trigger=trigger,
                previous_size=pos_size,
            )

            if close_ok:
                triggered += 1
                self.protective_orders_service.cancel_exchange_protective_orders(coin)
                self.position_manager.remove_position(coin)
                self._send_trigger_notification(trigger, coin, entry_price, trigger_price, current_price)
                self._record_trigger_trade(coin, close_size, current_price, result, action_info, trigger)
                self.metrics.increment("trades_executed_total")
                logger.info(f"{trigger.upper()} close executed for {coin}")
            else:
                logger.error(f"Failed to execute {trigger} close for {coin} after retries: {result}")

        return triggered