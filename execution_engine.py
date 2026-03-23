import logging
import time
from decimal import Decimal, ROUND_UP
from typing import Any, Dict

from exchange_client import HyperliquidExchangeClient
from models import MarketData, TradingAction
from utils.decimals import safe_decimal

logger = logging.getLogger(__name__)


class ExecutionEngine:
    MIN_ORDER_NOTIONAL_USD = Decimal("10")
    MARKET_BUFFER_PCT = Decimal("0.02")  # 2% aggressivo per aumentare fill immediato

    def __init__(self, exchange_client: HyperliquidExchangeClient):
        self.exchange_client = exchange_client
        self.allowed_actions = {action.value for action in TradingAction}
        self._leverage_cache_by_coin: Dict[str, Dict[str, Any]] = {}
        self._leverage_cache_ttl_sec = 300.0  # 5 minuti

    def _adjust_open_size_for_exchange_minimum(self, coin: str, size: Decimal, price: Decimal) -> Decimal:
        """
        Adegua la size per rispettare il minimo notional dell'exchange ($10) su ordini di apertura/incremento.
        Non modifica action o leverage scelti dall'LLM.
        """
        if size <= 0 or price <= 0:
            return size

        notional = size * price
        if notional >= self.MIN_ORDER_NOTIONAL_USD:
            return size

        required_size = self.MIN_ORDER_NOTIONAL_USD / price
        sz_decimals = self.exchange_client.get_sz_decimals(coin)

        if sz_decimals is None or sz_decimals < 0:
            return required_size

        step = Decimal("1").scaleb(-sz_decimals)
        adjusted = (required_size / step).to_integral_value(rounding=ROUND_UP) * step
        return adjusted

    def _is_leverage_cached(self, coin: str, leverage: int) -> bool:
        cached = self._leverage_cache_by_coin.get(coin)
        if not cached:
            return False

        cached_leverage = int(cached.get("leverage", -1))
        cached_at = float(cached.get("ts", 0.0))
        if cached_leverage != int(leverage):
            return False

        age = time.time() - cached_at
        return age <= self._leverage_cache_ttl_sec

    def _remember_leverage(self, coin: str, leverage: int) -> None:
        self._leverage_cache_by_coin[coin] = {
            "leverage": int(leverage),
            "ts": time.time(),
        }

    def _invalidate_leverage_cache(self, coin: str) -> None:
        if coin in self._leverage_cache_by_coin:
            del self._leverage_cache_by_coin[coin]

    def _set_leverage(self, coin: str, leverage: int, force: bool = False) -> bool:
        """
        Imposta leva con identità fissa (nessun fallback vault/utente alternativo).
        Ottimizzazione: se già impostata di recente alla stessa leva, salta la chiamata.
        """
        if not force and self._is_leverage_cached(coin, leverage):
            logger.debug(f"Skip set leverage for {coin}: cached {leverage}x")
            return True

        ok = self.exchange_client.set_leverage(coin, leverage)
        if ok:
            self._remember_leverage(coin, leverage)
            return True

        self._invalidate_leverage_cache(coin)
        return False

    def _market_desired_price(self, side: str, base_price: Decimal) -> Decimal:
        if base_price <= 0:
            return base_price
        normalized_side = str(side).strip().lower()
        if normalized_side == "buy":
            return base_price * (Decimal("1") + self.MARKET_BUFFER_PCT)
        return base_price * (Decimal("1") - self.MARKET_BUFFER_PCT)

    def execute(
        self,
        coin: str,
        order: Dict[str, Any],
        market_data: MarketData,
        positions: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        action = str(order.get("action", "")).strip().lower()
        size = safe_decimal(order.get("size", 0))
        leverage = int(safe_decimal(order.get("leverage", 1)))

        if action not in self.allowed_actions:
            return {"success": False, "notional": Decimal("0"), "reason": "unknown_action"}

        if action == TradingAction.HOLD.value:
            return {"success": True, "notional": Decimal("0"), "reason": "hold"}

        if action == TradingAction.CHANGE_LEVERAGE.value:
            if coin not in positions:
                return {"success": False, "notional": Decimal("0"), "reason": "no_position_for_leverage_change"}
            ok = self._set_leverage(coin, leverage, force=True)
            return {"success": ok, "notional": Decimal("0"), "reason": "change_leverage"}

        if action == TradingAction.CLOSE_POSITION.value:
            if coin not in positions:
                return {"success": False, "notional": Decimal("0"), "reason": "no_position_to_close"}
            pos_size = safe_decimal(positions[coin]["size"])
            side = "sell" if pos_size > 0 else "buy"
            close_size = abs(pos_size)
            desired_price = self._market_desired_price(side, market_data.last_price)
            result = self.exchange_client.place_order(coin, side, close_size, desired_price, reduce_only=True)
            executed_size = safe_decimal(result.get("executed_size", close_size))
            if executed_size <= 0:
                executed_size = close_size
            return {
                "success": bool(result.get("success", False)),
                "notional": safe_decimal(result.get("notional", "0")),
                "filled_price": safe_decimal(result.get("filled_price", desired_price)),
                "executed_size": executed_size,
                "reason": "close_position"
            }

        if action == TradingAction.REDUCE_POSITION.value:
            if coin not in positions:
                return {"success": False, "notional": Decimal("0"), "reason": "no_position_to_reduce"}
            pos_size = safe_decimal(positions[coin]["size"])
            current_size = abs(pos_size)
            reduce_size = size if size <= current_size else current_size
            side = "sell" if pos_size > 0 else "buy"
            desired_price = self._market_desired_price(side, market_data.last_price)
            result = self.exchange_client.place_order(coin, side, reduce_size, desired_price, reduce_only=True)
            executed_size = safe_decimal(result.get("executed_size", reduce_size))
            if executed_size <= 0:
                executed_size = reduce_size
            return {
                "success": bool(result.get("success", False)),
                "notional": safe_decimal(result.get("notional", "0")),
                "filled_price": safe_decimal(result.get("filled_price", desired_price)),
                "executed_size": executed_size,
                "reason": "reduce_position"
            }

        if action == TradingAction.INCREASE_POSITION.value:
            if coin not in positions:
                return {"success": False, "notional": Decimal("0"), "reason": "no_position_to_increase"}
            pos_size = safe_decimal(positions[coin]["size"])
            side = "buy" if pos_size > 0 else "sell"
            if not self._set_leverage(coin, leverage):
                return {"success": False, "notional": Decimal("0"), "reason": "set_leverage_failed"}

            adjusted_size = self._adjust_open_size_for_exchange_minimum(coin, size, market_data.last_price)
            desired_price = self._market_desired_price(side, market_data.last_price)
            result = self.exchange_client.place_order(coin, side, adjusted_size, desired_price)
            executed_size = safe_decimal(result.get("executed_size", adjusted_size))
            if executed_size <= 0:
                executed_size = adjusted_size
            return {
                "success": bool(result.get("success", False)),
                "notional": safe_decimal(result.get("notional", "0")),
                "filled_price": safe_decimal(result.get("filled_price", desired_price)),
                "executed_size": executed_size,
                "reason": "increase_position"
            }

        if action in [TradingAction.BUY.value, TradingAction.SELL.value]:
            side = "buy" if action == TradingAction.BUY.value else "sell"
            if not self._set_leverage(coin, leverage):
                return {"success": False, "notional": Decimal("0"), "reason": "set_leverage_failed"}

            adjusted_size = self._adjust_open_size_for_exchange_minimum(coin, size, market_data.last_price)
            desired_price = self._market_desired_price(side, market_data.last_price)

            # Flusso sequenziale: prima entry, poi protezioni in fase successiva (PositionManager/ProtectiveOrdersService)
            result = self.exchange_client.place_order(coin, side, adjusted_size, desired_price)

            executed_size = safe_decimal(result.get("executed_size", adjusted_size))
            if executed_size <= 0:
                executed_size = adjusted_size

            return {
                "success": bool(result.get("success", False)),
                "notional": safe_decimal(result.get("notional", "0")),
                "filled_price": safe_decimal(result.get("filled_price", desired_price)),
                "executed_size": executed_size,
                "reason": "open_position_sequential",
                "entry_with_protection": False,
            }

        return {"success": False, "notional": Decimal("0"), "reason": "unhandled_action"}