import logging
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ProtectiveOrdersService:
    """Protective TP/SL reconciliation workflow used by exchange facade."""

    def __init__(self, client, order_query_service):
        self.client = client
        self.order_query = order_query_service

    def upsert_protective_orders(
        self,
        coin: str,
        position_size: Decimal,
        is_long: bool,
        stop_loss_price: Decimal,
        take_profit_price: Decimal,
        current_stop_order_id: Optional[int] = None,
        current_take_profit_order_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not self.client._live_orders_enabled():
            return {"success": False, "reason": "live_disabled_fail_closed"}

        trading_user = self.client.get_trading_user_address()
        close_side = "sell" if is_long else "buy"
        close_size = abs(position_size)
        if close_size <= 0:
            return {"success": False, "reason": "invalid_size"}

        existing_sl_id = current_stop_order_id
        existing_tp_id = current_take_profit_order_id

        if existing_sl_id is None:
            existing_sl_id = self.order_query.wait_for_trigger_order_id(
                user=trading_user,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=stop_loss_price,
                tpsl="sl",
                attempts=3,
                delay_sec=0.3,
            )

        if existing_tp_id is None:
            existing_tp_id = self.order_query.wait_for_trigger_order_id(
                user=trading_user,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=take_profit_price,
                tpsl="tp",
                attempts=3,
                delay_sec=0.3,
            )

        if existing_sl_id is not None and existing_tp_id is not None:
            self.order_query.cancel_duplicate_trigger_orders(
                user=trading_user,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=stop_loss_price,
                tpsl="sl",
                keep_oid=existing_sl_id,
            )
            self.order_query.cancel_duplicate_trigger_orders(
                user=trading_user,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=take_profit_price,
                tpsl="tp",
                keep_oid=existing_tp_id,
            )
            return {
                "success": True,
                "stop_loss_order_id": existing_sl_id,
                "take_profit_order_id": existing_tp_id,
            }

        cancelled = self.order_query.cancel_existing_coin_protective_orders(trading_user, coin, close_side)
        if cancelled > 0:
            logger.warning(f"Cancelled {cancelled} stale protective trigger orders for {coin} side={close_side.upper()}")

        if current_stop_order_id is not None:
            self.client.cancel_order(coin, current_stop_order_id)
        if current_take_profit_order_id is not None:
            self.client.cancel_order(coin, current_take_profit_order_id)

        is_close_buy = close_side == "buy"
        orders = [
            {
                "coin": coin,
                "is_buy": is_close_buy,
                "sz": close_size,
                "limit_px": stop_loss_price,
                "order_type": {"trigger": {"isMarket": True, "triggerPx": stop_loss_price, "tpsl": "sl"}},
                "reduce_only": True,
            },
            {
                "coin": coin,
                "is_buy": is_close_buy,
                "sz": close_size,
                "limit_px": take_profit_price,
                "order_type": {"trigger": {"isMarket": True, "triggerPx": take_profit_price, "tpsl": "tp"}},
                "reduce_only": True,
            },
        ]

        bulk_res = self.client.bulk_orders(orders, grouping="normalTpsl")
        if not bulk_res.get("success"):
            return {"success": False, "reason": f"bulk_tpsl_failed:{bulk_res.get('reason', 'unknown')}"}

        sl_id = self.order_query.wait_for_trigger_order_id(
            user=trading_user,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=stop_loss_price,
            tpsl="sl",
            attempts=8,
            delay_sec=0.5,
        )
        tp_id = self.order_query.wait_for_trigger_order_id(
            user=trading_user,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=take_profit_price,
            tpsl="tp",
            attempts=8,
            delay_sec=0.5,
        )

        if sl_id is None:
            sl_id = self.order_query.find_latest_protective_order_id(
                user=trading_user,
                coin=coin,
                side=close_side,
                tpsl="sl",
            )
        if tp_id is None:
            tp_id = self.order_query.find_latest_protective_order_id(
                user=trading_user,
                coin=coin,
                side=close_side,
                tpsl="tp",
            )

        if sl_id is None or tp_id is None:
            return {"success": False, "reason": "missing_trigger_order_id_after_bulk"}

        self.order_query.cancel_duplicate_trigger_orders(
            user=trading_user,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=stop_loss_price,
            tpsl="sl",
            keep_oid=sl_id,
        )
        self.order_query.cancel_duplicate_trigger_orders(
            user=trading_user,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=take_profit_price,
            tpsl="tp",
            keep_oid=tp_id,
        )

        return {
            "success": True,
            "stop_loss_order_id": sl_id,
            "take_profit_order_id": tp_id,
        }