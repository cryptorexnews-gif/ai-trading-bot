"""
Writes bot live status to shared JSON file.
The API server reads this file to serve real-time data.
"""

import json
import time
from decimal import Decimal
from typing import Any, Dict, Optional

from utils.file_io import atomic_write_json


LIVE_STATUS_PATH = "state/bot_live_status.json"


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def write_live_status(
    is_running: bool,
    execution_mode: str,
    cycle_count: int,
    last_cycle_duration: float,
    portfolio: Optional[Dict[str, Any]] = None,
    current_coin: str = "",
    last_decision: Optional[Dict[str, Any]] = None,
    error: str = ""
) -> None:
    """Write current bot status to shared file for API server."""
    status = {
        "is_running": is_running,
        "execution_mode": execution_mode,
        "cycle_count": cycle_count,
        "last_cycle_duration": round(last_cycle_duration, 2),
        "current_coin": current_coin,
        "last_decision": _serialize_decision(last_decision) if last_decision else None,
        "portfolio": _serialize_portfolio(portfolio) if portfolio else {},
        "error": error,
        "updated_at": time.time()
    }

    atomic_write_json(LIVE_STATUS_PATH, status, cls=_DecimalEncoder)


def _serialize_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    result = {}
    for key, value in decision.items():
        if isinstance(value, Decimal):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def _serialize_portfolio(portfolio) -> Dict[str, Any]:
    if portfolio is None:
        return {}
    if hasattr(portfolio, "total_balance"):
        positions_serialized = {}
        for coin, pos in portfolio.positions.items():
            positions_serialized[coin] = {
                k: float(v) if isinstance(v, Decimal) else v
                for k, v in pos.items()
            }
        return {
            "total_balance": float(portfolio.total_balance),
            "available_balance": float(portfolio.available_balance),
            "margin_usage": float(portfolio.margin_usage),
            "total_exposure": float(portfolio.get_total_exposure()),
            "total_unrealized_pnl": float(portfolio.get_total_unrealized_pnl()),
            "positions": positions_serialized,
            "position_count": len(portfolio.positions)
        }
    if isinstance(portfolio, dict):
        return portfolio
    return {}