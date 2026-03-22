from decimal import Decimal
from typing import Any, Dict, List, Optional


def build_managed_position_context(position_manager, coin: str) -> Optional[Dict[str, Any]]:
    managed = position_manager.get_position(coin)
    if not managed:
        return None

    sl_price = managed.stop_loss.calculate_stop_price(managed.entry_price, managed.is_long)
    if managed.break_even.activated and managed.stop_loss.price is not None:
        sl_price = managed.stop_loss.price
    tp_price = managed.take_profit.calculate_tp_price(managed.entry_price, managed.is_long)

    return {
        "coin": managed.coin,
        "is_long": managed.is_long,
        "size": str(managed.size),
        "entry_price": str(managed.entry_price),
        "stop_loss_pct": str(managed.stop_loss.percentage),
        "take_profit_pct": str(managed.take_profit.percentage),
        "stop_loss_price": str(sl_price),
        "take_profit_price": str(tp_price),
        "break_even_activated": bool(managed.break_even.activated),
        "stop_loss_order_id": managed.stop_loss_order_id,
        "take_profit_order_id": managed.take_profit_order_id,
    }


def extract_protective_orders_for_coin(exchange_client, coin: str) -> List[Dict[str, Any]]:
    trading_user = exchange_client.get_trading_user_address()
    open_orders = exchange_client.get_open_orders(trading_user, force_refresh=True)

    protective_orders: List[Dict[str, Any]] = []
    target_coin = str(coin or "").strip().upper()

    for order in open_orders:
        order_coin = _extract_order_coin(order)
        if order_coin != target_coin:
            continue

        tpsl = _extract_order_tpsl(order)
        if tpsl not in {"tp", "sl"}:
            continue

        protective_orders.append({
            "oid": _extract_order_oid(order),
            "coin": order_coin,
            "tpsl": tpsl,
            "trigger_px": str(_extract_order_trigger_px(order)),
            "side": _extract_order_side(order),
            "reduce_only": _extract_order_reduce_only(order),
        })

    protective_orders.sort(key=lambda o: (o.get("tpsl", ""), o.get("oid") or 0))
    return protective_orders


def has_both_tp_sl(orders: List[Dict[str, Any]]) -> bool:
    has_sl = any(str(o.get("tpsl", "")).lower() == "sl" for o in orders if isinstance(o, dict))
    has_tp = any(str(o.get("tpsl", "")).lower() == "tp" for o in orders if isinstance(o, dict))
    return has_sl and has_tp


def _extract_order_coin(order: Dict[str, Any]) -> str:
    if not isinstance(order, dict):
        return ""
    coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
    if coin:
        return coin
    nested = order.get("order", {})
    if isinstance(nested, dict):
        return str(nested.get("coin", nested.get("symbol", ""))).strip().upper()
    return ""


def _extract_order_oid(order: Dict[str, Any]) -> Optional[int]:
    if not isinstance(order, dict):
        return None
    direct = order.get("oid")
    if direct is not None:
        return int(direct)

    nested = order.get("order", {})
    if isinstance(nested, dict):
        nested_oid = nested.get("oid")
        if nested_oid is not None:
            return int(nested_oid)

    resting = order.get("resting", {})
    if isinstance(resting, dict):
        resting_oid = resting.get("oid")
        if resting_oid is not None:
            return int(resting_oid)
    return None


def _extract_order_side(order: Dict[str, Any]) -> str:
    def norm(v: Any) -> str:
        raw = str(v or "").strip().lower()
        if raw in {"b", "buy", "bid", "long", "true"}:
            return "buy"
        if raw in {"a", "s", "sell", "ask", "short", "false"}:
            return "sell"
        return ""

    if not isinstance(order, dict):
        return ""

    for candidate in [order.get("side"), order.get("dir"), order.get("b")]:
        side = norm(candidate)
        if side:
            return side

    nested = order.get("order", {})
    if isinstance(nested, dict):
        for candidate in [nested.get("side"), nested.get("dir"), nested.get("b")]:
            side = norm(candidate)
            if side:
                return side

    return ""


def _extract_order_tpsl(order: Dict[str, Any]) -> str:
    if not isinstance(order, dict):
        return ""

    candidates: List[Any] = [order.get("tpsl"), order.get("triggerType")]
    trigger_obj = order.get("trigger", {})
    if isinstance(trigger_obj, dict):
        candidates.append(trigger_obj.get("tpsl"))
        candidates.append(trigger_obj.get("triggerType"))

    order_type = order.get("orderType", {})
    if isinstance(order_type, dict):
        trigger_obj_2 = order_type.get("trigger", {})
        if isinstance(trigger_obj_2, dict):
            candidates.append(trigger_obj_2.get("tpsl"))
            candidates.append(trigger_obj_2.get("triggerType"))

    nested = order.get("order", {})
    if isinstance(nested, dict):
        candidates.append(nested.get("tpsl"))
        candidates.append(nested.get("triggerType"))
        nested_trigger = nested.get("trigger", {})
        if isinstance(nested_trigger, dict):
            candidates.append(nested_trigger.get("tpsl"))
            candidates.append(nested_trigger.get("triggerType"))

    for candidate in candidates:
        value = str(candidate or "").strip().lower()
        if value in {"tp", "sl"}:
            return value

    if bool(order.get("isTp")):
        return "tp"
    if bool(order.get("isSl")):
        return "sl"

    return ""


def _extract_order_trigger_px(order: Dict[str, Any]) -> Decimal:
    if not isinstance(order, dict):
        return Decimal("0")

    def d(v: Any) -> Decimal:
        if v is None:
            return Decimal("0")
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0")

    candidates: List[Any] = [order.get("triggerPx"), order.get("tpTriggerPx"), order.get("slTriggerPx")]

    trigger_obj = order.get("trigger", {})
    if isinstance(trigger_obj, dict):
        candidates.append(trigger_obj.get("triggerPx"))

    order_type = order.get("orderType", {})
    if isinstance(order_type, dict):
        trigger_obj_2 = order_type.get("trigger", {})
        if isinstance(trigger_obj_2, dict):
            candidates.append(trigger_obj_2.get("triggerPx"))

    nested = order.get("order", {})
    if isinstance(nested, dict):
        candidates.extend([nested.get("triggerPx"), nested.get("tpTriggerPx"), nested.get("slTriggerPx")])
        nested_trigger = nested.get("trigger", {})
        if isinstance(nested_trigger, dict):
            candidates.append(nested_trigger.get("triggerPx"))
        nested_order_type = nested.get("orderType", {})
        if isinstance(nested_order_type, dict):
            nested_trigger_2 = nested_order_type.get("trigger", {})
            if isinstance(nested_trigger_2, dict):
                candidates.append(nested_trigger_2.get("triggerPx"))

    for c in candidates:
        px = d(c)
        if px > 0:
            return px

    return Decimal("0")


def _extract_order_reduce_only(order: Dict[str, Any]) -> bool:
    if not isinstance(order, dict):
        return False

    candidates: List[Any] = [order.get("r"), order.get("reduceOnly"), order.get("isReduceOnly")]
    nested = order.get("order", {})
    if isinstance(nested, dict):
        candidates.extend([nested.get("r"), nested.get("reduceOnly"), nested.get("isReduceOnly")])

    for c in candidates:
        if isinstance(c, bool) and c:
            return True
        if str(c).strip().lower() in {"true", "1"}:
            return True

    return False