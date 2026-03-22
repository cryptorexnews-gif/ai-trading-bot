import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ProtectiveOrdersService:
    """Protective TP/SL reconciliation workflow used by exchange facade."""

    def __init__(self, client, order_query_service):
        self.client = client
        self.order_query = order_query_service

    def _submit_single_trigger_order_via_bulk(
        self,
        coin: str,
        is_close_buy: bool,
        close_size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
    ) -> Dict[str, Any]:
        order = {
            "coin": coin,
            "is_buy": is_close_buy,
            "sz": close_size,
            "limit_px": trigger_price,
            "order_type": {"trigger": {"isMarket": True, "triggerPx": trigger_price, "tpsl": tpsl}},
            "reduce_only": True,
        }
        return self.client.bulk_orders([order], grouping="positionTpsl")

    def _wait_or_find_trigger_oid(
        self,
        user: str,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
    ) -> Optional[int]:
        oid = self.client._wait_for_trigger_order_id(
            user=user,
            coin=coin,
            side=side,
            size=size,
            trigger_price=trigger_price,
            tpsl=tpsl,
            attempts=8,
            delay_sec=0.5,
        )
        if oid is not None:
            return oid

        return self.client._find_latest_protective_order_id(
            user=user,
            coin=coin,
            side=side,
            tpsl=tpsl,
        )

    def _fallback_upsert_sequential(
        self,
        trading_user: str,
        coin: str,
        close_side: str,
        close_size: Decimal,
        stop_loss_price: Decimal,
        take_profit_price: Decimal,
    ) -> Tuple[bool, Optional[int], Optional[int], str]:
        is_close_buy = close_side == "buy"

        sl_bulk = self._submit_single_trigger_order_via_bulk(
            coin=coin,
            is_close_buy=is_close_buy,
            close_size=close_size,
            trigger_price=stop_loss_price,
            tpsl="sl",
        )
        if not sl_bulk.get("success"):
            return False, None, None, f"sl_failed:{sl_bulk.get('reason', 'unknown')}"

        sl_id = self._wait_or_find_trigger_oid(
            user=trading_user,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=stop_loss_price,
            tpsl="sl",
        )
        if sl_id is None:
            return False, None, None, "sl_missing_oid"

        tp_bulk = self._submit_single_trigger_order_via_bulk(
            coin=coin,
            is_close_buy=is_close_buy,
            close_size=close_size,
            trigger_price=take_profit_price,
            tpsl="tp",
        )
        if not tp_bulk.get("success"):
            self.client.cancel_order(coin, sl_id)
            return False, None, None, f"tp_failed:{tp_bulk.get('reason', 'unknown')}"

        tp_id = self._wait_or_find_trigger_oid(
            user=trading_user,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=take_profit_price,
            tpsl="tp",
        )
        if tp_id is None:
            self.client.cancel_order(coin, sl_id)
            return False, None, None, "tp_missing_oid"

        return True, sl_id, tp_id, "ok"

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

        bulk_res = self.client.bulk_orders(orders, grouping="positionTpsl")
        if not bulk_res.get("success"):
            logger.warning(
                f"Bulk TP/SL failed for {coin} ({bulk_res.get('reason', 'unknown')}), "
                "trying sequential SL->TP fallback"
            )
            ok, sl_id, tp_id, reason = self._fallback_upsert_sequential(
                trading_user=trading_user,
                coin=coin,
                close_side=close_side,
                close_size=close_size,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
            )
            if not ok:
                return {"success": False, "reason": f"bulk_tpsl_failed:{reason}"}

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