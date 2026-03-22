import hmac
import os
from functools import wraps

from flask import jsonify, request

from api.config import API_AUTH_KEY
from api.security_utils import env_bool, is_loopback_ip


def _is_server_loopback_bound() -> bool:
    host = os.getenv("API_HOST", "127.0.0.1").strip()
    return is_loopback_ip(host)


def _is_local_socket_request() -> bool:
    remote_addr = (request.remote_addr or "").strip()
    return is_loopback_ip(remote_addr)


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        allow_localhost_bypass = env_bool("ALLOW_LOCALHOST_BYPASS", True)

        if allow_localhost_bypass and _is_server_loopback_bound() and _is_local_socket_request():
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