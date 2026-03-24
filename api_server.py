"""
Flask API server entrypoint for the Hyperliquid bot dashboard.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from api import create_app
from api.config import API_AUTH_KEY, DASHBOARD_READ_API_KEY, CORS_ORIGINS
from api.security_utils import env_bool, is_loopback_ip

logger = logging.getLogger(__name__)
app = create_app()


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "5000"))
    debug = os.getenv("API_DEBUG", "false").lower() == "true"
    allow_localhost_bypass = env_bool("ALLOW_LOCALHOST_BYPASS", False)
    loopback_bound = is_loopback_ip(host)

    env_mode = os.getenv("EXECUTION_MODE", "live").lower()
    if env_mode != "live":
        logger.warning("EXECUTION_MODE is not 'live'. Runtime is now live-only; forcing live behavior.")

    if host == "0.0.0.0":
        logger.warning(
            "API server binding to 0.0.0.0 — ensure a reverse proxy with TLS is in front "
            "for production deployments."
        )

    api_key_status = "SET ✓" if API_AUTH_KEY else "EMPTY ✗"
    read_key_status = "SET ✓" if DASHBOARD_READ_API_KEY else "EMPTY ✗"
    logger.info(f"DASHBOARD_API_KEY (admin) status: {api_key_status} (length={len(API_AUTH_KEY) if API_AUTH_KEY else 0})")
    logger.info(f"DASHBOARD_READ_API_KEY (read-only) status: {read_key_status} (length={len(DASHBOARD_READ_API_KEY) if DASHBOARD_READ_API_KEY else 0})")

    auth_mode = "API key required"
    if allow_localhost_bypass and loopback_bound:
        auth_mode = "localhost loopback bypass enabled; remote/proxied requests require API key"

    logger.info(
        f"🚀 Starting API server on http://{host}:{port} "
        f"(mode=live, debug={debug}, auth={auth_mode}, CORS: {CORS_ORIGINS})"
    )
    logger.info(f"API Server ready: http://{host}:{port}")
    if allow_localhost_bypass and loopback_bound:
        logger.info("Local direct loopback requests: ALLOWED without API key")
        logger.info("Forwarded/non-loopback requests: API key required")
    else:
        logger.info("API key required for protected endpoints (GET supports read-only key if configured)")
    logger.info("Health endpoint available at /api/health")

    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()