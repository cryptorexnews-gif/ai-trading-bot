"""
Log viewer endpoint — serves recent logs with sensitive data sanitized.
"""

import json
import os
import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import LOG_FILE
from api.helpers import sanitize_log_message

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("/api/logs", methods=["GET"])
@require_api_key
def logs():
    """Return recent logs with sensitive data redacted."""
    limit = request.args.get("limit", 100, type=int)
    limit = min(limit, 200)

    if not os.path.exists(LOG_FILE):
        return jsonify({"logs": [], "timestamp": time.time()})

    try:
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
    except IOError:
        return jsonify({"logs": [], "timestamp": time.time()})