"""
Log viewer endpoint — serves recent logs with sensitive data sanitized.
"""

import json
import logging
import os
import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import LOG_FILE
from api.helpers import sanitize_log_message
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

logs_bp = Blueprint("logs", __name__)
_logs_rl = get_rate_limiter("api_logs_endpoint", max_tokens=30, tokens_per_second=1.0)


@logs_bp.route("/api/logs", methods=["GET"])
@require_api_key
def logs():
    if not _logs_rl.try_acquire(1):
        return jsonify({"error": "rate_limited"}), 429

    limit = request.args.get("limit", 100, type=int)
    if limit is None or limit < 1 or limit > 200:
        return jsonify({"error": "invalid_request"}), 400

    try:
        if not os.path.exists(LOG_FILE):
            return jsonify({"logs": [], "timestamp": time.time()})

        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        recent_lines = lines[-limit:]
        log_entries = []
        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if "message" in entry:
                    entry["message"] = sanitize_log_message(str(entry["message"]))
                if "exception" in entry:
                    entry["exception"] = sanitize_log_message(str(entry["exception"]))
                log_entries.append(entry)
            except json.JSONDecodeError:
                log_entries.append({
                    "message": sanitize_log_message(line),
                    "level": "INFO"
                })

        return jsonify({
            "logs": list(reversed(log_entries)),
            "total_lines": len(lines),
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Logs endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500