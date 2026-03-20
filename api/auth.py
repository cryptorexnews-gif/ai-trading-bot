import hmac
import os
from functools import wraps
from ipaddress import ip_address

from flask import jsonify, request

from api.config import API_AUTH_KEY


def _env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean env values robustly."""
    val = os.getenv(key, "").strip().lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def _is_loopback_ip(value: str) -> bool:
    """Return True if value is a loopback IP (supports IPv4, IPv6, mapped IPv6)."""
    if not value:
        return False

    candidate = value.strip()

    # Handle possible "host:port" style
    if candidate.count(":") == 1 and "." in candidate:
        candidate = candidate.split(":", 1)[0]

    # Handle IPv6-mapped IPv4
    if candidate.startswith("::ffff:"):
        candidate = candidate.replace("::ffff:", "", 1)

    try:
        return ip_address(candidate).is_loopback
    except ValueError:
        return candidate in ("localhost",)


def _is_localhost_request() -> bool:
    """
    Determine if request originates from localhost.
    Checks direct remote address and forwarded headers used by local proxies/dev servers.
    """
    remote_addr = (request.remote_addr or "").strip()

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    forwarded_ip = forwarded_for.split(",")[0].strip() if forwarded_for else ""

    real_ip = (request.headers.get("X-Real-IP", "") or "").strip()

    host_header = (request.host or "").split(":")[0].strip().lower()

    return any(
        _is_loopback_ip(v)
        for v in (remote_addr, forwarded_ip, real_ip, host_header)
    )


def require_api_key(f):
    """Decorator to require X-API-Key header on protected endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        execution_mode = os.getenv("EXECUTION_MODE", "paper").strip().lower()
        allow_localhost_bypass = _env_bool("ALLOW_LOCALHOST_BYPASS", True)

        # In non-live mode, localhost is allowed by default for local DX.
        if execution_mode != "live" and allow_localhost_bypass and _is_localhost_request():
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