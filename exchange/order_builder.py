from decimal import Decimal
from typing import Any, Dict


def _decimal_to_wire_str(value: Decimal) -> str:
    """
    Converte Decimal in stringa plain (no notazione scientifica),
    mantenendo precisione e rimuovendo zeri finali non necessari.
    """
    q = format(value, "f")
    if "." in q:
        q = q.rstrip("0").rstrip(".")
    return q if q else "0"


def build_limit_order_action(
    asset_id: int,
    is_buy: bool,
    price: Decimal,
    size: Decimal,
    reduce_only: bool = False,
    tif: str = "Ioc",
) -> Dict[str, Any]:
    if tif not in {"Ioc", "Gtc", "Alo"}:
        tif = "Ioc"

    order_wire = {
        "a": asset_id,
        "b": is_buy,
        "p": _decimal_to_wire_str(price),
        "s": _decimal_to_wire_str(size),
        "r": bool(reduce_only),
        "t": {"limit": {"tif": tif}},
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
    grouping: str = "na",
) -> Dict[str, Any]:
    trigger_str = _decimal_to_wire_str(trigger_price)
    order_wire = {
        "a": asset_id,
        "b": is_buy,
        "p": trigger_str,
        "s": _decimal_to_wire_str(size),
        "r": bool(reduce_only),
        "t": {
            "trigger": {
                "triggerPx": trigger_str,
                "isMarket": bool(is_market),
                "tpsl": tpsl,
            }
        },
    }
    return {"type": "order", "orders": [order_wire], "grouping": grouping}


def build_cancel_action(asset_id: int, order_id: int) -> Dict[str, Any]:
    return {"type": "cancel", "cancels": [{"a": asset_id, "o": int(order_id)}]}


def build_update_leverage_action(asset_id: int, leverage: int) -> Dict[str, Any]:
    return {"type": "updateLeverage", "asset": asset_id, "isCross": True, "leverage": int(leverage)}