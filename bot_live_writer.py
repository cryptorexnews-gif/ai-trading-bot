"""
Scrive stato bot live su file JSON condiviso.
Il server API legge questo file per servire dati in tempo reale.
"""

import json
import os
import time
from decimal import Decimal
from typing import Any, Dict, Optional


LIVE_STATUS_PATH = "state/bot_live_status.json"


class DecimalEncoder(json.JSONEncoder):
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
    """Scrivi stato corrente bot su file condiviso per server API."""
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

    os.makedirs(os.path.dirname(LIVE_STATUS_PATH) or ".", exist_ok=True)
    tmp_path = LIVE_STATUS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2, cls=DecimalEncoder)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, LIVE_STATUS_PATH)


def _serialize_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    """Serializza un dizionario decisione, convertendo Decimal."""
    result = {}
    for key, value in decision.items():
        if isinstance(value, Decimal):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def _serialize_portfolio(portfolio) -> Dict[str, Any]:
    """Serializza stato portfolio per JSON."""
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