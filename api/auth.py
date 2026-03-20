import hmac
import os
from functools import wraps

from flask import jsonify, request

from api.config import API_AUTH_KEY


def _is_localhost_request() -> bool:
    """Allow localhost only by direct remote_addr check."""
    remote_addr = request.remote_addr or ""
    return remote_addr in ("127.0.0.1", "::1")


def require_api_key(f):
    """Decorator to require X-API-Key header on protected endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()
        allow_localhost_bypass = os.getenv("ALLOW_LOCALHOST_BYPASS", "true").lower() == "true"

        bypass_allowed = allow_localhost_bypass and execution_mode != "live" and _is_localhost_request()
        if bypass_allowed:
            return f(*args, **kwargs)

        if not API_AUTH_KEY:
            return jsonify({"error": "unauthorized"}), 401

        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key:
            return jsonify({"error": "unauthorized"}), 401

        if not hmac.compare_digest(provided_key.encode("utf-8"), API_AUTH_KEY.encode("utf-8")):
            return jsonify({"error": "unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated