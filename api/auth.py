import hmac
import os
from functools import wraps
from ipaddress import ip_address

from flask import jsonify, request

from api.config import API_AUTH_KEY


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "").strip().lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def _is_loopback_ip(value: str) -> bool:
    if not value:
        return False

    candidate = value.strip()

    # Handle IPv6-mapped IPv4
    if candidate.startswith("::ffff:"):
        candidate = candidate.replace("::ffff:", "", 1)

    # Handle simple host:port for IPv4 forms
    if candidate.count(":") == 1 and "." in candidate:
        candidate = candidate.split(":", 1)[0]

    try:
        return ip_address(candidate).is_loopback
    except ValueError:
        return candidate in ("localhost",)


def _is_server_loopback_bound() -> bool:
    host = os.getenv("API_HOST", "127.0.0.1").strip()
    return _is_loopback_ip(host)


def _is_local_socket_request() -> bool:
    # Security: trust ONLY the real socket peer address.
    # Do not trust X-Forwarded-For / X-Real-IP / Host for auth decisions.
    remote_addr = (request.remote_addr or "").strip()
    return _is_loopback_ip(remote_addr)


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        execution_mode = os.getenv("EXECUTION_MODE", "paper").strip().lower()
        allow_localhost_bypass = _env_bool("ALLOW_LOCALHOST_BYPASS", True)

        if (
            execution_mode != "live"
            and allow_localhost_bypass
            and _is_server_loopback_bound()
            and _is_local_socket_request()
        ):
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