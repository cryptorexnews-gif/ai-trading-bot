"""
Prometheus metrics endpoint — exports bot metrics in text format.
"""

from flask import Blueprint, Response

from api.auth import require_api_key
from api.config import LIVE_STATUS_PATH, STATE_PATH, METRICS_PATH
from api.services.metrics_service import build_prometheus_metrics_lines
from api.services.status_snapshot_service import load_status_snapshot
from state_store import StateStore

metrics_bp = Blueprint("metrics", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)


@metrics_bp.route("/metrics", methods=["GET"])
@require_api_key
def prometheus_metrics():
    """Export bot metrics in Prometheus text format."""
    snapshot = load_status_snapshot(_state_store, LIVE_STATUS_PATH)

    lines = build_prometheus_metrics_lines(
        metrics_data=snapshot["metrics"],
        live_status=snapshot["live_status"],
        state=snapshot["state"],
        cb_states=snapshot["circuit_breakers"],
    )

    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain; version=0.0.4; charset=utf-8"
    )