import hmac
import os
from functools import wraps

from flask import jsonify, request

from api.config import API_AUTH_KEY


def require_api_key(f):
    """Decorator to require X-API-Key header on protected endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_AUTH_KEY:
            # In live mode, refuse to run without an API key
            execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()
            if execution_mode == "live":
                return jsonify({
                    "error": "unauthorized",
                    "message": "DASHBOARD_API_KEY must be set when EXECUTION_MODE=live"
                }), 401
            # Paper/dev mode — allow access without key (with startup warning)
            return f(*args, **kwargs)

        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key:
            return jsonify({"error": "unauthorized"}), 401

        # Timing-safe comparison to prevent timing attacks
        if not hmac.compare_digest(provided_key.encode("utf-8"), API_AUTH_KEY.encode("utf-8")):
            return jsonify({"error": "unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated