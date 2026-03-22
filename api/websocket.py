import hmac
import json
import os
import time
from decimal import Decimal
from ipaddress import ip_address
from typing import Any, Dict

from flask import request
from flask_sock import Sock

from api.config import API_AUTH_KEY, LIVE_STATUS_PATH, METRICS_PATH, STATE_PATH
from api.helpers import post_hyperliquid_info, read_json_file
from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states
from utils.rate_limiter import get_all_rate_limiter_stats

sock = Sock()
_state_store = StateStore(STATE_PATH, METRICS_PATH)


def _is_loopback_ip(value: str) -> bool:
    if not value:
        return False

    candidate = value.strip()
    if candidate.startswith("::ffff:"):
        candidate = candidate.replace("::ffff:", "", 1)

    if candidate.count(":") == 1 and "." in candidate:
        candidate = candidate.split(":", 1)[0]

    try:
        return ip_address(candidate).is_loopback
    except ValueError:
        return candidate in ("localhost",)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if raw in ("true", "1", "yes", "on"):
        return True
    if raw in ("false", "0", "no", "off"):
        return False
    return default


def _is_authorized() -> bool:
    allow_localhost_bypass = _env_bool("ALLOW_LOCALHOST_BYPASS", True)
    api_host = os.getenv("API_HOST", "127.0.0.1").strip()
    remote_addr = (request.remote_addr or "").strip()

    if allow_localhost_bypass and _is_loopback_ip(api_host) and _is_loopback_ip(remote_addr):
        return True

    if not API_AUTH_KEY:
        return False

    provided = request.args.get("api_key", "")
    return hmac.compare_digest(provided.encode("utf-8"), API_AUTH_KEY.encode("utf-8"))


def _json_default(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _build_status_payload() -> Dict[str, Any]:
    live_status = read_json_file(LIVE_STATUS_PATH)
    state = _state_store.load_state()
    metrics = _state_store.load_metrics()

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
        "circuit_breakers": get_all_circuit_states(),
        "rate_limiters": get_all_rate_limiter_stats(),
    }


@sock.route("/ws/status")
def ws_status(ws):
    if not _is_authorized():
        ws.close()
        return

    while True:
        payload = _build_status_payload()
        ws.send(json.dumps(payload, default=_json_default))
        time.sleep(1.0)


@sock.route("/ws/market")
def ws_market(ws):
    if not _is_authorized():
        ws.close()
        return

    coin = str(request.args.get("coin", "")).strip().upper()

    while True:
        mids = post_hyperliquid_info({"type": "allMids"}, timeout=15)
        if not isinstance(mids, dict):
            mids = {}

        if coin:
            payload = {
                "type": "market",
                "timestamp": time.time(),
                "coin": coin,
                "mid": mids.get(coin),
            }
        else:
            payload = {
                "type": "market",
                "timestamp": time.time(),
                "mids": mids,
            }

        ws.send(json.dumps(payload, default=_json_default))
        time.sleep(1.0)