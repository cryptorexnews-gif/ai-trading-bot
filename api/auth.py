"""
API key authentication for dashboard endpoints.
"""

from functools import wraps

from flask import jsonify, request

from api.config import API_AUTH_KEY


def require_api_key(f):
    """Decorator to require X-API-Key header on protected endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_AUTH_KEY:
            # No key configured — allow access (development mode)
            return f(*args, **kwargs)
        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key or provided_key != API_AUTH_KEY:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated