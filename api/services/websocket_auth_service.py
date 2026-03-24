import hmac
import os

from flask import request

from api.security_utils import env_bool, is_loopback_ip


def _is_server_loopback_bound() -> bool:
    host = os.getenv("API_HOST", "127.0.0.1").strip()
    return is_loopback_ip(host)


def _has_forwarded_headers() -> bool:
    forwarded_indicators = [
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Forwarded-Proto",
        "Forwarded",
    ]
    return any(bool(request.headers.get(h, "").strip()) for h in forwarded_indicators)


def _is_local_socket_request() -> bool:
    remote_addr = (request.remote_addr or "").strip()
    if not is_loopback_ip(remote_addr):
        return False

    if _has_forwarded_headers():
        return False

    return True


def is_ws_authorized(api_auth_key: str) -> bool:
    # Security default: bypass disabled unless explicitly enabled
    allow_localhost_bypass = env_bool("ALLOW_LOCALHOST_BYPASS", False)

    if allow_localhost_bypass and _is_server_loopback_bound() and _is_local_socket_request():
        return True

    if not api_auth_key:
        return False

    # Security: query-string API keys are forbidden
    provided_header = request.headers.get("X-API-Key", "")
    if not provided_header:
        return False

    return hmac.compare_digest(provided_header.encode("utf-8"), api_auth_key.encode("utf-8"))