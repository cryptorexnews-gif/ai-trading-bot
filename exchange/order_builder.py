from decimal import Decimal
from typing import Any, Dict, List, Optional


def _decimal_to_wire_str(value: Decimal) -> str:
    """
    Converte Decimal in stringa plain (no notazione scientifica),
    mantenendo precisione e rimuovendo zeri finali non necessari.
    """
    q = format(value, "f")
    if "." in q:
        q = q.rstrip("0").rstrip(".")
    return q if q else "0"


def _ensure_wire_types(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure all values in the order wire dict are plain Python types
    that msgpack serializes consistently.
    Decimal/float in the wire dict cause different msgpack bytes = different EIP-712 hash
    = different recovered signer address.
    """
    result = {}
    for key, value in order.items():
        if isinstance(value, Decimal):
            result[key] = _decimal_to_wire_str(value)
        elif isinstance(value, dict):
            result[key] = _ensure_wire_types(value)
        elif isinstance(value, list):
            result[key] = [_ensure_wire_types(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value
    return result


def build_limit_order_action(
    asset_id: int,
    is_buy: bool,
    price: Decimal,
    size: Decimal,
    reduce_only: bool = False,
    tif: str = "Ioc",
    price_str: Optional[str] = None,
    size_str: Optional[str] = None,
) -> Dict[str, Any]:
    if tif not in {"Ioc", "Gtc", "Alo"}:
        tif = "Ioc"

    order_wire = {
        "a": int(asset_id),
        "b": bool(is_buy),
        "p": price_str if price_str is not None else _decimal_to_wire_str(price),
        "s": size_str if size_str is not None else _decimal_to_wire_str(size),
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
    trigger_price_str: Optional[str] = None,
    size_str: Optional[str] = None,
) -> Dict[str, Any]:
    effective_trigger_str = trigger_price_str if trigger_price_str is not None else _decimal_to_wire_str(trigger_price)
    effective_size_str = size_str if size_str is not None else _decimal_to_wire_str(size)

    # Hyperliquid trigger order rules:
    # - For atomic batch (grouping="positionTpsl"), p="0" is allowed
    # - For standalone (grouping="na"), p must be the trigger price itself
    if grouping == "positionTpsl":
        limit_price_str = "0" if bool(is_market) else effective_trigger_str
    else:
        # Standalone trigger: p = triggerPx (required by Hyperliquid)
        limit_price_str = effective_trigger_str

    order_wire = {
        "a": int(asset_id),
        "b": bool(is_buy),
        "p": str(limit_price_str),
        "s": str(effective_size_str),
        "r": bool(reduce_only),
        "t": {
            "trigger": {
                "isMarket": bool(is_market),
                "triggerPx": str(effective_trigger_str),
                "tpsl": str(tpsl),
            }
        },
    }
    return {"type": "order", "orders": [order_wire], "grouping": str(grouping)}


def build_cancel_action(asset_id: int, order_id: int) -> Dict[str, Any]:
    return {"type": "cancel", "cancels": [{"a": int(asset_id), "o": int(order_id)}]}


def build_update_leverage_action(asset_id: int, leverage: int) -> Dict[str, Any]:
    return {"type": "updateLeverage", "asset": int(asset_id), "isCross": True, "leverage": int(leverage)}