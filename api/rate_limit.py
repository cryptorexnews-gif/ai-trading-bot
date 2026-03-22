from functools import wraps

from flask import jsonify

from utils.rate_limiter import get_rate_limiter


def rate_limited(name: str, max_tokens: int, tokens_per_second: float):
    """Decorator factory for endpoint-level token bucket rate limiting."""
    limiter = get_rate_limiter(name, max_tokens=max_tokens, tokens_per_second=tokens_per_second)

    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if not limiter.try_acquire(1):
                return jsonify({"error": "rate_limited"}), 429
            return func(*args, **kwargs)
        return wrapped

    return decorator