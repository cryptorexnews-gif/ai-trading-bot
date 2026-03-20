"""
Flask API server entrypoint for the Hyperliquid bot dashboard.
"""

import logging
import os

from api import create_app
from api.config import API_AUTH_KEY, CORS_ORIGINS

logger = logging.getLogger(__name__)
app = create_app()


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "5000"))
    debug = os.getenv("API_DEBUG", "false").lower() == "true"
    execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()

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

    logger.info(
        f"🚀 Starting API server on http://{host}:{port} "
        f"(mode={execution_mode}, debug={debug}, CORS: {CORS_ORIGINS})"
    )
    print(f"\n✅ API Server ready: http://{host}:{port}")
    print("   Localhost access: ALLOWED (no API key required)")
    print("   Remote access: API key required")
    print(f"   Test: /api/health")
    print()

    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()