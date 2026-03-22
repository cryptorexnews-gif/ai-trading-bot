"""
Log viewer endpoint — serves recent logs with sensitive data sanitized.
"""

import logging
import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import LOG_FILE
from api.helpers import sanitize_log_message
from api.rate_limit import rate_limited
from api.services.log_service import read_recent_logs

logger = logging.getLogger(__name__)

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("/api/logs", methods=["GET"])
@require_api_key
@rate_limited("api_logs_endpoint", max_tokens=30, tokens_per_second=1.0)
def logs():
    limit = request.args.get("limit", 100, type=int)
    if limit is None or limit < 1 or limit > 200:
        return jsonify({"error": "invalid_request"}), 400

    try:
        entries, total_lines = read_recent_logs(
            log_file=LOG_FILE,
            limit=limit,
            sanitizer=sanitize_log_message,
        )
        return jsonify({
            "logs": entries,
            "total_lines": total_lines,
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Logs endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500