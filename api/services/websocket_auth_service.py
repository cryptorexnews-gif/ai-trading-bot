from flask import request

from api.security_utils import env_bool, is_loopback_ip


def is_ws_authorized(api_auth_key: str) -> bool:
    allow_localhost_bypass = env_bool("ALLOW_LOCALHOST_BYPASS", True)

    api_host = request.environ.get("SERVER_NAME", "")
    if not api_host:
        api_host = request.host.split(":")[0] if request.host else "127.0.0.1"

    remote_addr = (request.remote_addr or "").strip()

    if allow_localhost_bypass and is_loopback_ip(api_host) and is_loopback_ip(remote_addr):
        return True

    if not api_auth_key:
        return False

    provided_query = request.args.get("api_key", "")
    provided_header = request.headers.get("X-API-Key", "")
    provided = provided_query or provided_header

    if not provided:
        return False

    return provided == api_auth_key