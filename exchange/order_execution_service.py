import json
import logging
from decimal import Decimal
from typing import Any, Dict, List

from exchange.market_rules import format_price_for_hyperliquid
from exchange.order_builder import (
    build_cancel_action,
    build_limit_order_action,
    build_trigger_order_action,
    build_update_leverage_action,
)
from exchange.parsers import (
    extract_order_ids,
    extract_statuses,
    get_first_status_error,
    has_acknowledged_order_status,
)
from utils.decimals import safe_decimal

logger = logging.getLogger(__name__)


class OrderExecutionService:
    """Runs live exchange execution workflows using the client façade."""

    def __init__(self, client):
        self.client = client

    @staticmethod
    def _canonical_decimal_str(value: Any) -> str:
        dec = Decimal(str(value))
        plain = format(dec, "f")
        if "." in plain:
            plain = plain.rstrip("0").rstrip(".")
        return plain if plain else "0"

    def _format_price_for_asset(self, coin: str, price: Decimal) -> str:
        """
        Formatta prezzo per Hyperliquid:
        - arrotonda al tick size
        - formatta con il numero esatto di decimali della precisione
        - per precision=0 produce stringa intera senza punto decimale (es. "2015" non "2015.0")
        """
        asset_id = self.client.get_asset_id(coin)
        if asset_id is None:
            return self._canonical_decimal_str(price)

        rounded = self.client._round_price_to_tick(asset_id, price)
        _tick_size, precision = self.client.get_tick_size_and_precision(asset_id)

        if precision >= 0:
            if precision > 0:
                return f"{rounded:.{precision}f}"
            # precision == 0: integer format, no decimal point
            int_val = int(rounded)
            return str(int_val)

        # Fallback estremo
        sz_decimals = self.client.get_sz_decimals(coin)
        return format_price_for_hyperliquid(rounded, sz_decimals)

    def _format_size_for_coin(self, coin: str, size: Decimal) -> str:
        sz_decimals = self.client.get_sz_decimals(coin)
        if sz_decimals is None or sz_decimals < 0:
            return self._canonical_decimal_str(size)

        normalized = self.client._normalize_size_for_coin(coin, abs(size))
        if sz_decimals > 0:
            return f"{normalized:.{sz_decimals}f}"
        return f"{normalized:.0f}"

    def set_leverage(self, coin: str, leverage: int) -> bool:
        if not self.client._live_orders_enabled():
            logger.error("Live leverage blocked: EXECUTION_MODE must be live and ENABLE_MAINNET_TRADING=true")
            return False

        leverage = max(1, leverage)
        max_leverage = self.client.get_max_leverage(coin)
        if leverage > max_leverage:
            leverage = max_leverage

        asset_id = self.client.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for {coin}")
            return False

        action = build_update_leverage_action(asset_id=asset_id, leverage=leverage)
        result = self.client._post_signed_action_with_master_retry(action)
        if result is None:
            return False
        if self.client._is_ok_result(result):
            logger.info(f"LIVE leverage set {coin} -> {leverage}x")
            return True
        logger.error(f"Set leverage failed for {coin}: {result}")
        return False

    def place_order(self, coin: str, side: str, size: Decimal, desired_price: Decimal, reduce_only: bool = False) -> Dict[str, Any]:
        if not self.client._live_orders_enabled():
            return {"success": False, "mode": "live", "reason": "live_disabled_fail_closed", "notional": "0"}

        normalized_size = self.client._normalize_size_for_coin(coin, abs(size))
        if normalized_size <= 0:
            return {"success": False, "mode": "live", "reason": "invalid_size_after_normalization", "notional": "0"}

        asset_id = self.client.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for {coin}")
            return {"success": False, "mode": "live", "reason": "asset_not_found", "notional": "0"}

        normalized_side = side.lower()
        if normalized_side not in {"buy", "sell"}:
            return {"success": False, "mode": "live", "reason": "invalid_side", "notional": "0"}

        is_buy = normalized_side == "buy"
        limit_price = self.client._resolve_limit_price(coin=coin, side=normalized_side, desired_price=desired_price, asset_id=asset_id)
        if limit_price <= 0:
            return {"success": False, "mode": "live", "reason": "invalid_limit_price", "notional": "0"}

        price_wire = self._format_price_for_asset(coin, limit_price)
        size_wire = self._format_size_for_coin(coin, normalized_size)

        logger.info(
            f"{coin} limit order wire: raw_price={limit_price} -> price_wire={price_wire}, "
            f"raw_size={normalized_size} -> size_wire={size_wire}"
        )

        action = build_limit_order_action(
            asset_id=asset_id,
            is_buy=is_buy,
            price=limit_price,
            size=normalized_size,
            reduce_only=reduce_only,
            price_str=price_wire,
            size_str=size_wire,
        )

        result = self.client._post_signed_action_with_master_retry(action)
        if result is None:
            return {"success": False, "mode": "live", "reason": "http_error", "notional": "0"}
        if not self.client._is_ok_result(result):
            logger.error(f"Exchange rejected order for {coin}: {result}")
            return {"success": False, "mode": "live", "reason": "exchange_rejected", "notional": "0", "raw": result}

        statuses = extract_statuses(result)
        status_error = get_first_status_error(statuses)
        if status_error is not None:
            logger.error(f"Order status error for {coin}: {status_error} | statuses={statuses}")
            return {
                "success": False,
                "mode": "live",
                "reason": f"status_error:{status_error}",
                "notional": "0",
                "raw": result,
                "statuses": statuses,
            }

        if statuses and not has_acknowledged_order_status(statuses):
            logger.error(f"Order not acknowledged by Hyperliquid statuses for {coin}: {statuses}")
            return {
                "success": False,
                "mode": "live",
                "reason": "not_acknowledged",
                "notional": "0",
                "raw": result,
                "statuses": statuses,
            }

        order_ids = extract_order_ids(result)
        notional = abs(normalized_size * limit_price)
        logger.info(
            f"LIVE order success {coin} {normalized_side.upper()} size={normalized_size} "
            f"limit={limit_price} reduce_only={reduce_only} oids={order_ids}"
        )
        return {
            "success": True,
            "mode": "live",
            "filled_price": str(limit_price),
            "executed_size": str(normalized_size),
            "notional": str(notional),
        }

    def place_entry_with_tpsl_batch(
        self,
        coin: str,
        side: str,
        size: Decimal,
        desired_price: Decimal,
        stop_loss_price: Decimal,
        take_profit_price: Decimal,
    ) -> Dict[str, Any]:
        """
        Atomic batch order: entry + TP + SL with grouping='positionTpsl'.
        Only valid when all three orders are sent together.
        """
        if not self.client._live_orders_enabled():
            return {"success": False, "mode": "live", "reason": "live_disabled_fail_closed", "notional": "0"}

        normalized_side = str(side or "").strip().lower()
        if normalized_side not in {"buy", "sell"}:
            return {"success": False, "mode": "live", "reason": "invalid_side", "notional": "0"}

        normalized_size = self.client._normalize_size_for_coin(coin, abs(size))
        if normalized_size <= 0:
            return {"success": False, "mode": "live", "reason": "invalid_size_after_normalization", "notional": "0"}

        asset_id = self.client.get_asset_id(coin)
        if asset_id is None:
            return {"success": False, "mode": "live", "reason": "asset_not_found", "notional": "0"}

        entry_limit_price = self.client._resolve_limit_price(
            coin=coin,
            side=normalized_side,
            desired_price=desired_price,
            asset_id=asset_id,
        )
        if entry_limit_price <= 0:
            return {"success": False, "mode": "live", "reason": "invalid_limit_price", "notional": "0"}

        if stop_loss_price <= 0 or take_profit_price <= 0:
            return {"success": False, "mode": "live", "reason": "invalid_trigger_price", "notional": "0"}

        entry_price_wire = self._format_price_for_asset(coin, entry_limit_price)
        sl_price_wire = self._format_price_for_asset(coin, stop_loss_price)
        tp_price_wire = self._format_price_for_asset(coin, take_profit_price)
        size_wire = self._format_size_for_coin(coin, normalized_size)

        is_buy = normalized_side == "buy"
        close_is_buy = not is_buy

        entry_order = {
            "a": asset_id,
            "b": is_buy,
            "p": entry_price_wire,
            "s": size_wire,
            "r": False,
            "t": {"limit": {"tif": "Ioc"}},
        }

        tp_order = {
            "a": asset_id,
            "b": close_is_buy,
            "p": "0",
            "s": size_wire,
            "r": True,
            "t": {
                "trigger": {
                    "isMarket": True,
                    "triggerPx": tp_price_wire,
                    "tpsl": "tp",
                }
            },
        }

        sl_order = {
            "a": asset_id,
            "b": close_is_buy,
            "p": "0",
            "s": size_wire,
            "r": True,
            "t": {
                "trigger": {
                    "isMarket": True,
                    "triggerPx": sl_price_wire,
                    "tpsl": "sl",
                }
            },
        }

        action = {
            "type": "order",
            "orders": [entry_order, tp_order, sl_order],
            "grouping": "positionTpsl",
        }

        logger.debug(f"{coin} atomic entry+TP/SL payload:\n{json.dumps(action, indent=2)}")

        result = self.client._post_signed_action_with_master_retry(action)
        if result is None:
            return {"success": False, "mode": "live", "reason": "http_error", "notional": "0"}
        if not self.client._is_ok_result(result):
            logger.error(f"Exchange rejected atomic entry+TP/SL batch for {coin}: {result}")
            return {"success": False, "mode": "live", "reason": "exchange_rejected", "notional": "0", "raw": result}

        statuses = extract_statuses(result)
        status_error = get_first_status_error(statuses)
        if status_error is not None:
            logger.error(f"Atomic batch status error for {coin}: {status_error} | statuses={statuses}")
            return {
                "success": False,
                "mode": "live",
                "reason": f"status_error:{status_error}",
                "notional": "0",
                "raw": result,
                "statuses": statuses,
            }

        if statuses and not has_acknowledged_order_status(statuses):
            return {
                "success": False,
                "mode": "live",
                "reason": "not_acknowledged",
                "notional": "0",
                "raw": result,
                "statuses": statuses,
            }

        notional = abs(normalized_size * entry_limit_price)
        order_ids = extract_order_ids(result)
        logger.info(
            f"LIVE atomic entry+TP/SL success {coin} {normalized_side.upper()} "
            f"size={normalized_size} entry={entry_price_wire} tp={tp_price_wire} sl={sl_price_wire} "
            f"grouping=positionTpsl oids={order_ids}"
        )
        return {
            "success": True,
            "mode": "live",
            "filled_price": str(entry_limit_price),
            "executed_size": str(normalized_size),
            "notional": str(notional),
            "order_ids": order_ids,
            "entry_with_protection": True,
        }

    def place_trigger_order(
        self,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
        reduce_only: bool = True,
        is_market: bool = True,
    ) -> Dict[str, Any]:
        """
        Place a standalone trigger order (TP or SL).
        Uses grouping='na' — 'positionTpsl' is only valid in atomic batch with entry.
        p = triggerPx for standalone trigger orders.
        """
        if not self.client._live_orders_enabled():
            return {"success": False, "reason": "live_disabled_fail_closed"}

        if tpsl not in {"tp", "sl"}:
            return {"success": False, "reason": "invalid_tpsl"}

        normalized_side = side.lower()
        if normalized_side not in {"buy", "sell"}:
            return {"success": False, "reason": "invalid_side"}

        normalized_size = self.client._normalize_size_for_coin(coin, abs(size))
        if normalized_size <= 0:
            return {"success": False, "reason": "invalid_size_after_normalization"}

        asset_id = self.client.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for trigger order {coin}")
            return {"success": False, "reason": "asset_not_found"}

        rounded_trigger = self.client._round_price_to_tick(asset_id, trigger_price)
        if rounded_trigger <= 0:
            return {"success": False, "reason": "invalid_trigger_price"}

        # Format trigger price and size with tick-precise decimals
        trigger_price_wire = self._format_price_for_asset(coin, rounded_trigger)
        size_wire = self._format_size_for_coin(coin, normalized_size)

        logger.info(
            f"{coin} trigger order wire: {tpsl.upper()} {normalized_side.upper()} "
            f"raw_trigger={trigger_price} -> rounded={rounded_trigger} -> wire='{trigger_price_wire}', "
            f"size_wire='{size_wire}'"
        )

        existing_oid = self.client._wait_for_trigger_order_id(
            user=self.client._trading_user_address,
            coin=coin,
            side=normalized_side,
            size=normalized_size,
            trigger_price=rounded_trigger,
            tpsl=tpsl,
            attempts=1,
            delay_sec=0.0,
        )
        if existing_oid is not None:
            return {"success": True, "order_id": existing_oid}

        # IMPORTANT: standalone trigger orders use grouping="na"
        # "positionTpsl" is only valid when sent as atomic batch with entry order
        # p = triggerPx for standalone (not "0")
        action = build_trigger_order_action(
            asset_id=asset_id,
            is_buy=(normalized_side == "buy"),
            trigger_price=rounded_trigger,
            size=normalized_size,
            tpsl=tpsl,
            reduce_only=reduce_only,
            is_market=is_market,
            grouping="na",
            trigger_price_str=trigger_price_wire,
            size_str=size_wire,
        )

        logger.debug(f"{coin} trigger order payload: {json.dumps(action, indent=2)}")

        result = self.client._post_signed_action_with_master_retry(action)
        if result is None:
            return {"success": False, "reason": "http_error"}
        if not self.client._is_ok_result(result):
            logger.error(f"Exchange rejected trigger order for {coin}: {result}")
            return {"success": False, "reason": "exchange_rejected", "raw": result}

        statuses = extract_statuses(result)
        status_error = get_first_status_error(statuses)
        if status_error is not None:
            logger.error(f"Trigger order status error for {coin}: {status_error} | statuses={statuses}")
            return {
                "success": False,
                "reason": f"status_error:{status_error}",
                "raw": result,
                "statuses": statuses,
            }

        if statuses and not has_acknowledged_order_status(statuses):
            return {
                "success": False,
                "reason": "not_acknowledged",
                "raw": result,
                "statuses": statuses,
            }

        immediate_oids = extract_order_ids(result)
        if immediate_oids:
            return {"success": True, "order_id": int(immediate_oids[0])}

        order_id = self.client._wait_for_trigger_order_id(
            user=self.client._trading_user_address,
            coin=coin,
            side=normalized_side,
            size=normalized_size,
            trigger_price=rounded_trigger,
            tpsl=tpsl,
            attempts=16,
            delay_sec=0.75,
        )

        if order_id is not None:
            return {"success": True, "order_id": order_id}

        fallback_oid = self.client._find_latest_protective_order_id(
            user=self.client._trading_user_address,
            coin=coin,
            side=normalized_side,
            tpsl=tpsl,
        )
        if fallback_oid is not None:
            logger.warning(
                f"Trigger order accepted and mapped via fallback for {coin} {tpsl.upper()} "
                f"{normalized_side.upper()} oid={fallback_oid}"
            )
            return {"success": True, "order_id": fallback_oid}

        return {"success": False, "reason": "missing_trigger_order_id"}

    def bulk_orders(self, orders: List[Dict[str, Any]], grouping: str = "na") -> Dict[str, Any]:
        if not self.client._live_orders_enabled():
            return {"success": False, "reason": "live_disabled_fail_closed"}

        if not isinstance(orders, list) or len(orders) == 0:
            return {"success": False, "reason": "empty_orders"}

        wire_orders: List[Dict[str, Any]] = []

        for order in orders:
            coin = str(order.get("coin", "")).strip().upper()
            if not coin:
                return {"success": False, "reason": "missing_coin"}

            asset_id = self.client.get_asset_id(coin)
            if asset_id is None:
                return {"success": False, "reason": f"asset_not_found:{coin}"}

            is_buy = bool(order.get("is_buy", False))
            side = "buy" if is_buy else "sell"

            raw_size = safe_decimal(order.get("sz", "0"), Decimal("0"))
            normalized_size = self.client._normalize_size_for_coin(coin, abs(raw_size))
            if normalized_size <= 0:
                return {"success": False, "reason": f"invalid_size:{coin}"}

            order_type = order.get("order_type", {"limit": {"tif": "Gtc"}})
            if not isinstance(order_type, dict):
                return {"success": False, "reason": f"invalid_order_type:{coin}"}

            if "trigger" in order_type:
                trigger_obj = order_type.get("trigger", {})
                trigger_px = safe_decimal(trigger_obj.get("triggerPx", "0"), Decimal("0"))
                if trigger_px <= 0:
                    return {"success": False, "reason": f"invalid_trigger_px:{coin}"}

                rounded_trigger = self.client._round_price_to_tick(asset_id, trigger_px)
                is_market = bool(trigger_obj.get("isMarket", True))

                raw_px = safe_decimal(order.get("limit_px", "0"), Decimal("0"))
                if not is_market and raw_px <= 0:
                    return {"success": False, "reason": f"invalid_limit_px:{coin}"}

                rounded_px = Decimal("0") if is_market else self.client._round_price_to_tick(asset_id, raw_px)

                # Format trigger price with tick precision
                trigger_wire = self._format_price_for_asset(coin, rounded_trigger)

                order_type = {
                    "trigger": {
                        "isMarket": is_market,
                        "triggerPx": trigger_wire,
                        "tpsl": str(trigger_obj.get("tpsl", "")).strip().lower(),
                    }
                }
            else:
                raw_px = safe_decimal(order.get("limit_px", "0"), Decimal("0"))
                if raw_px <= 0:
                    return {"success": False, "reason": f"invalid_limit_px:{coin}"}
                rounded_px = self.client._resolve_limit_price(
                    coin=coin,
                    side=side,
                    desired_price=raw_px,
                    asset_id=asset_id,
                )

            reduce_only = bool(order.get("reduce_only", False))

            # Format all prices and sizes with tick precision
            price_wire = self._format_price_for_asset(coin, rounded_px) if rounded_px > 0 else "0"
            size_wire = self._format_size_for_coin(coin, normalized_size)

            wire_orders.append(
                {
                    "a": asset_id,
                    "b": is_buy,
                    "p": price_wire,
                    "s": size_wire,
                    "r": reduce_only,
                    "t": order_type,
                }
            )

        action = {"type": "order", "orders": wire_orders, "grouping": grouping}
        result = self.client._post_signed_action_with_master_retry(action)

        if result is None:
            return {"success": False, "reason": "http_error"}
        if not self.client._is_ok_result(result):
            return {"success": False, "reason": "exchange_rejected", "raw": result}

        statuses = extract_statuses(result)
        status_error = get_first_status_error(statuses)
        if status_error is not None:
            return {"success": False, "reason": f"status_error:{status_error}", "raw": result, "statuses": statuses}

        if statuses and not has_acknowledged_order_status(statuses):
            return {"success": False, "reason": "not_acknowledged", "raw": result, "statuses": statuses}

        return {"success": True, "order_ids": extract_order_ids(result), "raw": result}

    def cancel_order(self, coin: str, order_id: int) -> bool:
        if not self.client._live_orders_enabled():
            return False

        asset_id = self.client.get_asset_id(coin)
        if asset_id is None:
            return False

        action = build_cancel_action(asset_id=asset_id, order_id=order_id)
        result = self.client._post_signed_action_with_master_retry(action)
        if result is None:
            return False
        if not self.client._is_ok_result(result):
            return False

        logger.info(f"Cancel success {coin} oid={order_id}")
        return True