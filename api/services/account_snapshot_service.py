import time
from decimal import Decimal
from typing import Any, Dict, List

from api.helpers import post_hyperliquid_info
from utils.hyperliquid_state import get_account_balances, get_open_positions


def mask_wallet(wallet: str) -> str:
    if not wallet or len(wallet) < 12:
        return "not_configured"
    return f"{wallet[:6]}...{wallet[-4:]}"


def get_hyperliquid_account_snapshot(wallet: str) -> Dict[str, Any]:
    if not wallet:
        return {
            "wallet": "",
            "wallet_masked": "not_configured",
            "portfolio": {
                "total_balance": Decimal("0"),
                "available_balance": Decimal("0"),
                "margin_usage": Decimal("0"),
                "positions": {},
                "position_count": 0,
                "total_unrealized_pnl": Decimal("0"),
                "total_exposure": Decimal("0"),
                "open_orders_count": 0,
            },
            "margin_summary": {},
            "withdrawable": "0",
            "updated_at": time.time(),
        }

    user_state = post_hyperliquid_info({"type": "clearinghouseState", "user": wallet}, timeout=20)
    if not isinstance(user_state, dict):
        return {
            "wallet": wallet,
            "wallet_masked": mask_wallet(wallet),
            "portfolio": {
                "total_balance": Decimal("0"),
                "available_balance": Decimal("0"),
                "margin_usage": Decimal("0"),
                "positions": {},
                "position_count": 0,
                "total_unrealized_pnl": Decimal("0"),
                "total_exposure": Decimal("0"),
                "open_orders_count": 0,
            },
            "margin_summary": {},
            "withdrawable": "0",
            "updated_at": time.time(),
        }

    balances = get_account_balances(user_state)
    positions = get_open_positions(user_state)

    total_unrealized_pnl = Decimal("0")
    total_exposure = Decimal("0")
    for pos in positions.values():
        size = Decimal(str(pos.get("size", 0)))
        entry = Decimal(str(pos.get("entry_price", 0)))
        pnl = Decimal(str(pos.get("unrealized_pnl", 0)))
        total_unrealized_pnl += pnl
        total_exposure += abs(size * entry)

    open_orders = post_hyperliquid_info({"type": "openOrders", "user": wallet}, timeout=15)
    open_orders_count = len(open_orders) if isinstance(open_orders, list) else 0

    return {
        "wallet": wallet,
        "wallet_masked": mask_wallet(wallet),
        "portfolio": {
            "total_balance": balances["total_balance"],
            "available_balance": balances["available_balance"],
            "margin_usage": balances["margin_usage"],
            "positions": positions,
            "position_count": len(positions),
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_exposure": total_exposure,
            "open_orders_count": open_orders_count,
        },
        "margin_summary": user_state.get("marginSummary", {}),
        "withdrawable": user_state.get("withdrawable", "0"),
        "updated_at": time.time(),
    }


def fetch_hyperliquid_universe() -> List[str]:
    data = post_hyperliquid_info({"type": "meta"}, timeout=20)
    if not isinstance(data, dict):
        return []

    universe = data.get("universe", [])
    parsed = []
    for asset in universe:
        coin = str(asset.get("name", "")).strip().upper()
        if coin:
            parsed.append(coin)

    return sorted(set(parsed))