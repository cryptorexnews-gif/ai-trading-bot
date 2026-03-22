import hmac
import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict

from flask import request

try:
    from flask_sock import Sock  # type: ignore
    _WS_ENABLED = True
except ModuleNotFoundError:
    _WS_ENABLED = False

    class Sock:  # fallback no-op
        def init_app(self, app):
            return None

        def route(self, _path):
            def decorator(func):
                return func
            return decorator

from api.config import API_AUTH_KEY, LIVE_STATUS_PATH, METRICS_PATH, STATE_PATH
from api.helpers import post_hyperliquid_info, read_json_file
from api.security_utils import env_bool, is_loopback_ip
from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states
from utils.rate_limiter import get_all_rate_limiter_stats

logger = logging.getLogger(__name__)

sock = Sock()
_state_store = StateStore(STATE_PATH, METRICS_PATH)


def _is_authorized() -> bool:
    allow_localhost_bypass = env_bool("ALLOW_LOCALHOST_BYPASS", True)
    api_host = os.getenv("API_HOST", "127.0.0.1").strip()
    remote_addr = (request.remote_addr or "").strip()

    if allow_localhost_bypass and is_loopback_ip(api_host) and is_loopback_ip(remote_addr):
        return True

    if not API_AUTH_KEY:
        return False

    provided_query = request.args.get("api_key", "")
    provided_header = request.headers.get("X-API-Key", "")
    provided = provided_query or provided_header

    if not provided:
        return False

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
    if not _WS_ENABLED:
        logger.warning("WebSocket endpoint /ws/status requested but flask_sock is not installed")
        return

    if not _is_authorized():
        ws.close()
        return

    while True:
        payload = _build_status_payload()
        try:
            ws.send(json.dumps(payload, default=_json_default))
        except Exception:
            break
        time.sleep(1.0)


@sock.route("/ws/market")
def ws_market(ws):
    if not _WS_ENABLED:
        logger.warning("WebSocket endpoint /ws/market requested but flask_sock is not installed")
        return

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

        try:
            ws.send(json.dumps(payload, default=_json_default))
        except Exception:
            break
        time.sleep(1.0)