import time
from typing import Any, Dict


def build_status_ws_payload(
    live_status: Dict[str, Any],
    state: Dict[str, Any],
    metrics: Dict[str, Any],
    circuit_breakers: Dict[str, Any],
    rate_limiters: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "type": "status",
        "timestamp": time.time(),
        "bot": live_status,
        "state": {
            "peak_portfolio_value": state.get("peak_portfolio_value", "0"),
            "consecutive_failed_cycles": state.get("consecutive_failed_cycles", 0),
            "consecutive_losses": state.get("consecutive_losses", 0),
        },
        "metrics": metrics,
        "circuit_breakers": circuit_breakers,
        "rate_limiters": rate_limiters,
    }


def build_market_ws_payload(coin: str, mids: Dict[str, Any]) -> Dict[str, Any]:
    if coin:
        return {
            "type": "market",
            "timestamp": time.time(),
            "coin": coin,
            "mid": mids.get(coin),
        }

    return {
        "type": "market",
        "timestamp": time.time(),
        "mids": mids,
    }