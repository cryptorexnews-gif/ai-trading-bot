from typing import Any, Dict

from api.helpers import read_json_file
from utils.circuit_breaker import get_all_circuit_states
from utils.rate_limiter import get_all_rate_limiter_stats


def load_status_snapshot(state_store, live_status_path: str) -> Dict[str, Any]:
    return {
        "live_status": read_json_file(live_status_path),
        "state": state_store.load_state(),
        "metrics": state_store.load_metrics(),
        "circuit_breakers": get_all_circuit_states(),
        "rate_limiters": get_all_rate_limiter_stats(),
    }