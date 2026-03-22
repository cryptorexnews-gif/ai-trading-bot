import logging
from decimal import Decimal

from technical_analyzer_simple import technical_fetcher

logger = logging.getLogger(__name__)


class EmergencyDeriskService:
    """Handles emergency margin de-risk flow."""

    def __init__(
        self,
        notifier,
        risk_manager,
        position_manager,
        protective_orders_service,
        risk_trigger_service,
        portfolio_service,
        state_store,
        metrics,
        cfg,
    ):
        self.notifier = notifier
        self.risk_manager = risk_manager
        self.position_manager = position_manager
        self.protective_orders_service = protective_orders_service
        self.risk_trigger_service = risk_trigger_service
        self.portfolio_service = portfolio_service
        self.state_store = state_store
        self.metrics = metrics
        self.cfg = cfg

    def handle_emergency_derisk(self, portfolio):
        if not self.risk_manager.check_emergency_derisk(portfolio):
            return portfolio

        worst_coin = self.risk_manager.get_emergency_close_coin(portfolio)
        if not worst_coin:
            logger.warning("Emergency derisk: no position to close")
            return portfolio

        logger.warning(f"EMERGENCY DERISK: closing {worst_coin}")
        self.notifier.notify_emergency_derisk(worst_coin, "margin_usage_critical")

        pos_size = Decimal(str(portfolio.positions[worst_coin]["size"]))
        side = "sell" if pos_size > 0 else "buy"
        close_size = abs(pos_size)

        mids = technical_fetcher.get_all_mids()
        current_price = Decimal(str(mids.get(worst_coin, "0"))) if mids and worst_coin in mids else Decimal("0")

        if current_price > 0:
            close_ok, result = self.risk_trigger_service.execute_trigger_close_with_retries(
                coin=worst_coin,
                side=side,
                close_size=close_size,
                current_price=current_price,
                trigger="emergency",
                previous_size=pos_size,
            )
            if close_ok:
                self.protective_orders_service.cancel_exchange_protective_orders(worst_coin)
                self.position_manager.remove_position(worst_coin)
                logger.info(f"Emergency close executed for {worst_coin}")

                state = self.state_store.load_state()
                trade_record = {
                    "timestamp": __import__("time").time(),
                    "coin": worst_coin,
                    "action": "close_position",
                    "size": str(close_size),
                    "price": str(current_price),
                    "notional": str(result.get("notional", "0")),
                    "leverage": 1,
                    "confidence": 1.0,
                    "reasoning": "Emergency derisk: margin usage critical",
                    "success": True,
                    "mode": self.cfg.execution_mode,
                    "trigger": "emergency",
                    "order_status": "filled",
                }
                self.state_store.add_trade_record(state, trade_record)
                self.state_store.save_state(state)
                return self.portfolio_service.get_portfolio_state()

            logger.error(f"Emergency close FAILED for {worst_coin} after retries: {result}")

        return portfolio