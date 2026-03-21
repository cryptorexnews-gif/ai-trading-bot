"""
Flask API server entrypoint for the Hyperliquid bot dashboard.
"""

import logging
import os
from ipaddress import ip_address

from dotenv import load_dotenv

load_dotenv()

from api import create_app
from api.config import API_AUTH_KEY, CORS_ORIGINS

logger = logging.getLogger(__name__)
app = create_app()


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "").strip().lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def _is_loopback_host(host: str) -> bool:
    if not host:
        return False
    candidate = host.strip()
    if candidate == "localhost":
        return True
    try:
        return ip_address(candidate).is_loopback
    except ValueError:
        return False


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "5000"))
    debug = os.getenv("API_DEBUG", "false").lower() == "true"
    execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()
    allow_localhost_bypass = _env_bool("ALLOW_LOCALHOST_BYPASS", True)
    loopback_bound = _is_loopback_host(host)

    api_key_status = "SET ✓" if API_AUTH_KEY else "EMPTY ✗"
    logger.info(f"DASHBOARD_API_KEY status: {api_key_status} (length={len(API_AUTH_KEY) if API_AUTH_KEY else 0})")

    if host == "0.0.0.0":
        logger.warning(
            "API server binding to 0.0.0.0 — ensure a reverse proxy with TLS is in front "
            "for production deployments."
        )

    if execution_mode == "live" and debug:
        logger.warning("Forcing debug=False because EXECUTION_MODE=live")
        debug = False

    if allow_localhost_bypass and loopback_bound and execution_mode != "live":
        auth_mode = "localhost loopback bypass enabled; remote requires API key"
    else:
        auth_mode = "API key required"

    logger.info(
        f"🚀 Starting API server on http://{host}:{port} "
        f"(mode={execution_mode}, debug={debug}, auth={auth_mode}, CORS: {CORS_ORIGINS})"
    )
    logger.info(f"API Server ready: http://{host}:{port}")
    if allow_localhost_bypass and loopback_bound and execution_mode != "live":
        logger.info("Local loopback requests: ALLOWED without API key")
        logger.info("Non-loopback requests: API key required")
    else:
        logger.info("API key required for protected endpoints")
    logger.info("Health endpoint available at /api/health")

    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()