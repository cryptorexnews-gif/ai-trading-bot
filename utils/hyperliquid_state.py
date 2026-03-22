from decimal import Decimal
from typing import Any, Dict


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def get_account_balances(user_state: Dict[str, Any]) -> Dict[str, Decimal]:
    """
    Parse account balances from Hyperliquid clearinghouseState payload.

    Returns:
      - total_balance
      - available_balance (withdrawable, root field with fallback)
      - total_margin_used
      - margin_usage
    """
    margin_summary = user_state.get("marginSummary", {})

    total_balance = _to_decimal(margin_summary.get("accountValue", "0"))
    available_balance = _to_decimal(
        user_state.get("withdrawable", margin_summary.get("withdrawable", "0"))
    )
    total_margin_used = _to_decimal(margin_summary.get("totalMarginUsed", "0"))
    margin_usage = (
        (total_margin_used / total_balance) if total_balance > 0 else Decimal("0")
    )

    return {
        "total_balance": total_balance,
        "available_balance": available_balance,
        "total_margin_used": total_margin_used,
        "margin_usage": margin_usage,
    }


def get_open_positions(user_state: Dict[str, Any]) -> Dict[str, Dict[str, Decimal]]:
    """
    Parse open positions from Hyperliquid clearinghouseState payload.
    """
    positions: Dict[str, Dict[str, Decimal]] = {}

    for pos_wrapper in user_state.get("assetPositions", []):
        pos = pos_wrapper.get("position", {})
        coin = pos.get("coin", "")
        size = _to_decimal(pos.get("szi", "0"))

        if coin and size != 0:
            positions[coin] = {
                "size": size,
                "entry_price": _to_decimal(pos.get("entryPx", "0")),
                "unrealized_pnl": _to_decimal(pos.get("unrealizedPnl", "0")),
                "margin_used": _to_decimal(pos.get("marginUsed", "0")),
            }

    return positions