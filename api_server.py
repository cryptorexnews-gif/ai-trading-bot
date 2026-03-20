#!/usr/bin/env python3
"""
API Server entry point for Hyperliquid Trading Bot Dashboard.
All routes are defined in the api/ package as Flask Blueprints.

Usage:
    python api_server.py
"""

# LOAD .env FIRST - before ANY imports that read os.getenv()
from dotenv import load_dotenv
load_dotenv()  # This must be FIRST to populate os.environ for all subsequent imports

import logging
import os

from api import create_app
from api.config import API_AUTH_KEY, CORS_ORIGINS

logger = logging.getLogger(__name__)


def run_api_server(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    """Start the API server."""
    app = create_app()

    execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()

    # Debug: Print detected API key status
    api_key_status = "SET" if API_AUTH_KEY else "EMPTY"
    logger.info(f"DASHBOARD_API_KEY status: {api_key_status} (length={len(API_AUTH_KEY) if API_AUTH_KEY else 0})")

    # Security checks
    if not API_AUTH_KEY:
        if execution_mode == "live":
            logger.error(
                "SECURITY CRITICAL: DASHBOARD_API_KEY not set while EXECUTION_MODE=live. "
                "All dashboard endpoints will reject requests. "
                "Set DASHBOARD_API_KEY in .env to enable dashboard access."
            )
        else:
            logger.warning(
                "SECURITY WARNING: DASHBOARD_API_KEY not set — API endpoints are unauthenticated. "
                "Set DASHBOARD_API_KEY in .env for production use."
            )

    if host == "0.0.0.0":
        if not API_AUTH_KEY:
            logger.error(
                "SECURITY CRITICAL: API server binding to 0.0.0.0 (all interfaces) "
                "without DASHBOARD_API_KEY. This exposes the API to the network without authentication."
            )
        logger.warning(
            "API server binding to 0.0.0.0 — ensure a reverse proxy with TLS is in front "
            "for production deployments."
        )

    # Never use Flask debug mode in live trading
    if execution_mode == "live" and debug:
        logger.warning("Forcing debug=False because EXECUTION_MODE=live")
        debug = False

    logger.info(
        f"Starting API server on {host}:{port} "
        f"(mode={execution_mode}, debug={debug}, CORS origins: {CORS_ORIGINS})"
    )
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    from utils.logging_config import setup_logging
    setup_logging(log_level="INFO", json_format=False, console_output=True)

    host = os.getenv("API_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("API_SERVER_PORT", "5000"))
    execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()

    # Only enable debug in paper mode
    use_debug = execution_mode != "live"

    run_api_server(host=host, port=port, debug=use_debug)