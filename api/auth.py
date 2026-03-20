import os
from functools import wraps

from flask import jsonify, request

from api.config import API_AUTH_KEY


def _is_localhost_request() -> bool:
    """Check if request is from localhost (development mode)."""
    # Check direct remote address
    remote_addr = request.remote_addr
    if remote_addr in ('127.0.0.1', '::1', 'localhost'):
        return True
    
    # Check X-Forwarded-For header (for reverse proxy setups)
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        # Take the first IP in the chain
        first_ip = forwarded_for.split(',')[0].strip()
        if first_ip in ('127.0.0.1', '::1', 'localhost'):
            return True
    
    # Check Origin header for CORS requests
    origin = request.headers.get('Origin', '')
    if origin and ('localhost' in origin or '127.0.0.1' in origin):
        return True
    
    return False


def require_api_key(f):
    """Decorator to require X-API-Key header on protected endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Allow localhost requests without API key (development mode)
        if _is_localhost_request():
            return f(*args, **kwargs)
        
        # For non-localhost requests, require API key
        if not API_AUTH_KEY:
            return jsonify({
                "error": "unauthorized",
                "message": "DASHBOARD_API_KEY must be set for non-localhost access"
            }), 401

        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key:
            return jsonify({"error": "unauthorized"}), 401

        # Timing-safe comparison to prevent timing attacks
        import hmac
        if not hmac.compare_digest(provided_key.encode("utf-8"), API_AUTH_KEY.encode("utf-8")):
            return jsonify({"error": "unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated