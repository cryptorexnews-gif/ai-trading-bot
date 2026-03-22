import json
import logging
import time
from decimal import Decimal
from typing import Any, Dict

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
from api.helpers import post_hyperliquid_info
from api.services.status_snapshot_service import load_status_snapshot
from api.services.websocket_auth_service import is_ws_authorized
from api.services.websocket_service import build_market_ws_payload, build_status_ws_payload
from state_store import StateStore

logger = logging.getLogger(__name__)

sock = Sock()
_state_store = StateStore(STATE_PATH, METRICS_PATH)


def _json_default(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _build_status_payload() -> Dict[str, Any]:
    snapshot = load_status_snapshot(_state_store, LIVE_STATUS_PATH)

    return build_status_ws_payload(
        live_status=snapshot["live_status"],
        state=snapshot["state"],
        metrics=snapshot["metrics"],
        circuit_breakers=snapshot["circuit_breakers"],
        rate_limiters=snapshot["rate_limiters"],
    )


@sock.route("/ws/status")
def ws_status(ws):
    if not _WS_ENABLED:
        logger.warning("WebSocket endpoint /ws/status requested but flask_sock is not installed")
        return

    if not is_ws_authorized(API_AUTH_KEY):
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

    if not is_ws_authorized(API_AUTH_KEY):
        ws.close()
        return

    from flask import request

    coin = str(request.args.get("coin", "")).strip().upper()

    while True:
        mids = post_hyperliquid_info({"type": "allMids"}, timeout=15)
        if not isinstance(mids, dict):
            mids = {}

        payload = build_market_ws_payload(coin=coin, mids=mids)

        try:
            ws.send(json.dumps(payload, default=_json_default))
        except Exception:
            break
        time.sleep(1.0)