"""
Log viewer endpoint — serves recent logs with sensitive data sanitized.
"""

import logging
import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import LOG_FILE
from api.helpers import sanitize_log_message
from api.rate_limit_utils import build_rate_limiter, rate_limited_response
from api.services.log_service import read_recent_logs

logger = logging.getLogger(__name__)

logs_bp = Blueprint("logs", __name__)
_logs_rl = build_rate_limiter("api_logs_endpoint", max_tokens=30, tokens_per_second=1.0)


@logs_bp.route("/api/logs", methods=["GET"])
@require_api_key
def logs():
    rate_limit_resp = rate_limited_response(_logs_rl)
    if rate_limit_resp:
        return rate_limit_resp

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