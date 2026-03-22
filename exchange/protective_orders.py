TP protective order creation with confirmation and rollback, using same trading user as entry orders.">
import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ProtectiveOrdersService:
    """Protective TP/SL reconciliation workflow used by exchange facade."""

    def __init__(self, client, order_query_service):
        self.client = client
        self.order_query = order_query_service

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
            attempts=10,
            delay_sec=0.6,
        )
        if oid is not None:
            return oid

        return self.client._find_latest_protective_order_id(
            user=user,
            coin=coin,
            side=side,
            tpsl=tpsl,
        )

    def _place_single_protective_with_confirmation(
        self,
        trading_user: str,
        coin: str,
        close_side: str,
        close_size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
    ) -> Tuple[bool, Optional[int], str]:
        result = self.client.place_trigger_order(
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=trigger_price,
            tpsl=tpsl,
            reduce_only=True,
            is_market=True,
        )
        if not result.get("success"):
            return False, None, f"{tpsl}_failed:{result.get('reason', 'unknown')}"

        oid = result.get("order_id")
        if oid is not None:
            oid_int = int(oid)
            is_open = self.client.are_order_ids_open(
                user=trading_user,
                coin=coin,
                order_ids=[oid_int],
            )
            if is_open:
                return True, oid_int, "ok"

        resolved_oid = self._wait_or_find_trigger_oid(
            user=trading_user,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=trigger_price,
            tpsl=tpsl,
        )
        if resolved_oid is None:
            return False, None, f"{tpsl}_missing_oid"

        return True, resolved_oid, "ok"

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
            logger.warning(
                f"Cancelled {cancelled} stale protective trigger orders for {coin} side={close_side.upper()}"
            )

        if current_stop_order_id is not None:
            self.client.cancel_order(coin, current_stop_order_id)
        if current_take_profit_order_id is not None:
            self.client.cancel_order(coin, current_take_profit_order_id)

        logger.info(
            f"{coin} protective upsert sequential mode: using trading_user={trading_user} "
            f"(same wallet path as entry orders)"
        )

        sl_ok, sl_id, sl_reason = self._place_single_protective_with_confirmation(
            trading_user=trading_user,
            coin=coin,
            close_side=close_side,
            close_size=close_size,
            trigger_price=stop_loss_price,
            tpsl="sl",
        )
        if not sl_ok or sl_id is None:
            return {"success": False, "reason": f"sequential_{sl_reason}"}

        tp_ok, tp_id, tp_reason = self._place_single_protective_with_confirmation(
            trading_user=trading_user,
            coin=coin,
            close_side=close_side,
            close_size=close_size,
            trigger_price=take_profit_price,
            tpsl="tp",
        )
        if not tp_ok or tp_id is None:
            self.client.cancel_order(coin, sl_id)
            return {"success": False, "reason": f"sequential_{tp_reason}"}

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