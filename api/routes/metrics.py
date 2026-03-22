"""
Prometheus metrics endpoint — exports bot metrics in text format.
"""

from flask import Blueprint, Response

from api.auth import require_api_key
from api.config import LIVE_STATUS_PATH, STATE_PATH, METRICS_PATH
from api.helpers import read_json_file
from api.services.metrics_service import build_prometheus_metrics_lines
from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states

metrics_bp = Blueprint("metrics", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)


@metrics_bp.route("/metrics", methods=["GET"])
@require_api_key
def prometheus_metrics():
    """Export bot metrics in Prometheus text format."""
    metrics_data = _state_store.load_metrics()
    live_status = read_json_file(LIVE_STATUS_PATH)
    state = _state_store.load_state()
    cb_states = get_all_circuit_states()

    lines = build_prometheus_metrics_lines(
        metrics_data=metrics_data,
        live_status=live_status,
        state=state,
        cb_states=cb_states,
    )

    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain; version=0.0.4; charset=utf-8"
    )