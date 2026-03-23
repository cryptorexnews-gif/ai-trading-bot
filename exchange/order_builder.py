from decimal import Decimal
from typing import Any, Dict, Optional


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
    price_str: Optional[str] = None,
    size_str: Optional[str] = None,
) -> Dict[str, Any]:
    if tif not in {"Ioc", "Gtc", "Alo"}:
        tif = "Ioc"

    order_wire = {
        "a": asset_id,
        "b": is_buy,
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
    # Hyperliquid: per trigger market, p deve essere "0"
    limit_price_str = "0" if bool(is_market) else effective_trigger_str

    order_wire = {
        "a": asset_id,
        "b": is_buy,
        "p": limit_price_str,
        "s": effective_size_str,
        "r": bool(reduce_only),
        "t": {
            "trigger": {
                "isMarket": bool(is_market),
                "triggerPx": effective_trigger_str,
                "tpsl": tpsl,
            }
        },
    }
    return {"type": "order", "orders": [order_wire], "grouping": grouping}


def build_cancel_action(asset_id: int, order_id: int) -> Dict[str, Any]:
    return {"type": "cancel", "cancels": [{"a": asset_id, "o": int(order_id)}]}


def build_update_leverage_action(asset_id: int, leverage: int) -> Dict[str, Any]:
    return {"type": "updateLeverage", "asset": asset_id, "isCross": True, "leverage": int(leverage)}