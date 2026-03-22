from flask import jsonify

from utils.rate_limiter import get_rate_limiter


def build_rate_limiter(name: str, max_tokens: int, tokens_per_second: float):
    return get_rate_limiter(name, max_tokens=max_tokens, tokens_per_second=tokens_per_second)


def rate_limited_response(limiter):
    if not limiter.try_acquire(1):
        return jsonify({"error": "rate_limited"}), 429
    return None