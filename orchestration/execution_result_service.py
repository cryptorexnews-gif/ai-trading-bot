import time
from decimal import Decimal
from typing import Any, Dict, Tuple


def normalize_executed_price_and_size(
    result: Dict[str, Any],
    market_price: Decimal,
    requested_size: Decimal,
) -> Tuple[Decimal, Decimal]:
    executed_price = Decimal(str(result.get("filled_price", market_price)))
    if executed_price <= 0:
        executed_price = market_price

    executed_size = Decimal(str(result.get("executed_size", requested_size)))
    if executed_size <= 0:
        executed_size = requested_size

    return executed_price, executed_size


def build_trade_record(
    coin: str,
    decision: Dict[str, Any],
    executed_size: Decimal,
    executed_price: Decimal,
    result: Dict[str, Any],
    fill_status: str,
    execution_mode: str,
) -> Dict[str, Any]:
    return {
        "timestamp": time.time(),
        "coin": coin,
        "action": decision["action"],
        "size": str(executed_size),
        "price": str(executed_price),
        "notional": str(result.get("notional", "0")),
        "leverage": decision["leverage"],
        "confidence": decision["confidence"],
        "reasoning": decision.get("reasoning", ""),
        "success": result["success"],
        "mode": execution_mode,
        "trigger": "ai",
        "order_status": fill_status,
    }