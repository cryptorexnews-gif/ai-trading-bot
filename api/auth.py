import hmac
import os
import threading
import time
from functools import wraps
from typing import Dict

from flask import jsonify, request

from api.config import API_AUTH_KEY
from api.security_utils import env_bool, is_loopback_ip
from utils.rate_limiter import TokenBucketRateLimiter

_AUTH_RATE_LIMITERS: Dict[str, TokenBucketRateLimiter] = {}
_AUTH_RL_LOCK = threading.Lock()
_AUTH_RL_LAST_CLEANUP = 0.0
_AUTH_RL_CLEANUP_INTERVAL_SEC = 300.0
_AUTH_RL_STALE_SEC = 3600.0


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

    # Security: if request traversed a proxy, do not consider it local bypass-safe.
    if _has_forwarded_headers():
        return False

    return True


def _get_auth_rate_limiter_for_ip(client_ip: str) -> TokenBucketRateLimiter:
    global _AUTH_RL_LAST_CLEANUP
    now = time.time()

    with _AUTH_RL_LOCK:
        if now - _AUTH_RL_LAST_CLEANUP >= _AUTH_RL_CLEANUP_INTERVAL_SEC:
            stale_keys = []
            for key, limiter in _AUTH_RATE_LIMITERS.items():
                stats = limiter.get_stats()
                last_seen = float(stats.get("last_seen", 0.0)) if "last_seen" in stats else 0.0
                if last_seen > 0 and (now - last_seen) > _AUTH_RL_STALE_SEC:
                    stale_keys.append(key)
            for key in stale_keys:
                del _AUTH_RATE_LIMITERS[key]
            _AUTH_RL_LAST_CLEANUP = now

        limiter = _AUTH_RATE_LIMITERS.get(client_ip)
        if limiter is None:
            limiter = TokenBucketRateLimiter(
                name=f"api_auth_ip_{client_ip}",
                max_tokens=30,
                tokens_per_second=0.5,
            )
            _AUTH_RATE_LIMITERS[client_ip] = limiter

        return limiter


def _auth_rate_limit_exceeded() -> bool:
    client_ip = (request.remote_addr or "unknown").strip() or "unknown"
    limiter = _get_auth_rate_limiter_for_ip(client_ip)
    return not limiter.try_acquire(1)


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Pre-auth brute-force guard
        if _auth_rate_limit_exceeded():
            return jsonify({"error": "rate_limited"}), 429

        # Security default: bypass disabled unless explicitly enabled
        allow_localhost_bypass = env_bool("ALLOW_LOCALHOST_BYPASS", False)

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