from decimal import Decimal
from typing import Any, Dict


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def get_account_balances(user_state: Dict[str, Any]) -> Dict[str, Decimal]:
    """
    Parse account balances from Hyperliquid clearinghouseState payload.

    Returns:
      - total_balance
      - available_balance (withdrawable, root field with fallback)
      - total_margin_used
      - margin_usage
    """
    if not isinstance(user_state, dict):
        return {
            "total_balance": Decimal("0"),
            "available_balance": Decimal("0"),
            "total_margin_used": Decimal("0"),
            "margin_usage": Decimal("0"),
        }

    margin_summary = user_state.get("marginSummary", {})
    if not isinstance(margin_summary, dict):
        margin_summary = {}

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

    if not isinstance(user_state, dict):
        return positions

    asset_positions = user_state.get("assetPositions", [])
    if not isinstance(asset_positions, list):
        return positions

    for pos_wrapper in asset_positions:
        if not isinstance(pos_wrapper, dict):
            continue

        pos = pos_wrapper.get("position", {})
        if not isinstance(pos, dict):
            continue

        coin = str(pos.get("coin", "")).strip().upper()
        if not coin:
            continue

        size = _to_decimal(pos.get("szi", "0"))
        if size == 0:
            continue

        positions[coin] = {
            "size": size,
            "entry_price": _to_decimal(pos.get("entryPx", "0")),
            "unrealized_pnl": _to_decimal(pos.get("unrealizedPnl", "0")),
            "margin_used": _to_decimal(pos.get("marginUsed", "0")),
        }

    return positions