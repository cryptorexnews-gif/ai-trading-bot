from decimal import Decimal
from typing import Any, Dict


def build_limit_order_action(
    asset_id: int,
    is_buy: bool,
    price: Decimal,
    size: Decimal,
    reduce_only: bool = False,
) -> Dict[str, Any]:
    order_wire = {
        "a": asset_id,
        "b": is_buy,
        "p": str(price),
        "s": str(size.normalize()),
        "r": bool(reduce_only),
        "t": {"limit": {"tif": "Gtc"}},
    }
    return {"type": "order", "orders": [order_wire], "grouping": "na"}


def build_trigger_order_action(
    asset_id: int,
    is_buy: bool,
    trigger_price: Decimal,
    size: Decimal,
    tpsl: str,
    reduce_only: bool = True,
    is_market: bool = True,
) -> Dict[str, Any]:
    order_wire = {
        "a": asset_id,
        "b": is_buy,
        "p": str(trigger_price),
        "s": str(size.normalize()),
        "r": bool(reduce_only),
        "t": {"trigger": {"isMarket": bool(is_market), "triggerPx": str(trigger_price), "tpsl": tpsl}},
    }
    return {"type": "order", "orders": [order_wire], "grouping": "positionTpsl"}


def build_cancel_action(asset_id: int, order_id: int) -> Dict[str, Any]:
    return {"type": "cancel", "cancels": [{"a": asset_id, "o": int(order_id)}]}


def build_update_leverage_action(asset_id: int, leverage: int) -> Dict[str, Any]:
    return {"type": "updateLeverage", "asset": asset_id, "isCross": True, "leverage": int(leverage)}