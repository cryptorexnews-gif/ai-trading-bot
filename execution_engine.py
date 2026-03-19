from decimal import Decimal
from typing import Any, Dict

from exchange_client import HyperliquidExchangeClient
from models import MarketData, TradingAction


class ExecutionEngine:
    def __init__(self, exchange_client: HyperliquidExchangeClient):
        self.exchange_client = exchange_client
        self.allowed_actions = {action.value for action in TradingAction}

    def _safe_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        return Decimal(str(value)) if value is not None else default

    def execute(
        self,
        coin: str,
        order: Dict[str, Any],
        market_data: MarketData,
        positions: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        action = str(order.get("action", "")).strip().lower()
        size = self._safe_decimal(order.get("size", 0))
        leverage = int(order.get("leverage", 1))

        if action not in self.allowed_actions:
            return {"success": False, "notional": Decimal("0"), "reason": "unknown_action"}

        if action == TradingAction.HOLD.value:
            return {"success": True, "notional": Decimal("0"), "reason": "hold"}

        if action == TradingAction.CHANGE_LEVERAGE.value:
            if coin not in positions:
                return {"success": False, "notional": Decimal("0"), "reason": "no_position_for_leverage_change"}
            ok = self.exchange_client.set_leverage(coin, leverage)
            return {"success": ok, "notional": Decimal("0"), "reason": "change_leverage"}

        if action == TradingAction.CLOSE_POSITION.value:
            if coin not in positions:
                return {"success": False, "notional": Decimal("0"), "reason": "no_position_to_close"}
            pos_size = self._safe_decimal(positions[coin]["size"])
            side = "sell" if pos_size > 0 else "buy"
            close_size = abs(pos_size)
            result = self.exchange_client.place_order(coin, side, close_size, market_data.last_price)
            return {
                "success": bool(result.get("success", False)),
                "notional": self._safe_decimal(result.get("notional", "0")),
                "reason": "close_position"
            }

        if action == TradingAction.REDUCE_POSITION.value:
            if coin not in positions:
                return {"success": False, "notional": Decimal("0"), "reason": "no_position_to_reduce"}
            pos_size = self._safe_decimal(positions[coin]["size"])
            current_size = abs(pos_size)
            reduce_size = size if size <= current_size else current_size
            side = "sell" if pos_size > 0 else "buy"
            result = self.exchange_client.place_order(coin, side, reduce_size, market_data.last_price)
            return {
                "success": bool(result.get("success", False)),
                "notional": self._safe_decimal(result.get("notional", "0")),
                "reason": "reduce_position"
            }

        if action == TradingAction.INCREASE_POSITION.value:
            if coin not in positions:
                return {"success": False, "notional": Decimal("0"), "reason": "no_position_to_increase"}
            pos_size = self._safe_decimal(positions[coin]["size"])
            side = "buy" if pos_size > 0 else "sell"
            if not self.exchange_client.set_leverage(coin, leverage):
                return {"success": False, "notional": Decimal("0"), "reason": "set_leverage_failed"}
            result = self.exchange_client.place_order(coin, side, size, market_data.last_price)
            return {
                "success": bool(result.get("success", False)),
                "notional": self._safe_decimal(result.get("notional", "0")),
                "reason": "increase_position"
            }

        if action in [TradingAction.BUY.value, TradingAction.SELL.value]:
            side = "buy" if action == TradingAction.BUY.value else "sell"
            if not self.exchange_client.set_leverage(coin, leverage):
                return {"success": False, "notional": Decimal("0"), "reason": "set_leverage_failed"}
            result = self.exchange_client.place_order(coin, side, size, market_data.last_price)
            return {
                "success": bool(result.get("success", False)),
                "notional": self._safe_decimal(result.get("notional", "0")),
                "reason": "open_position"
            }

        return {"success": False, "notional": Decimal("0"), "reason": "unhandled_action"}