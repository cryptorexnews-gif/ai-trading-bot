#!/usr/bin/env python3
"""
API Server entry point for Hyperliquid Trading Bot Dashboard.
All routes are defined in the api/ package as Flask Blueprints.

Usage:
    python api_server.py
"""

import logging
import os

from api import create_app
from api.config import API_AUTH_KEY, CORS_ORIGINS

logger = logging.getLogger(__name__)


def run_api_server(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    """Start the API server."""
    app = create_app()

    if not API_AUTH_KEY:
        logger.warning(
            "SECURITY WARNING: DASHBOARD_API_KEY not set — API endpoints are unauthenticated. "
            "Set DASHBOARD_API_KEY in .env for production use."
        )
    logger.info(f"Starting API server on {host}:{port} (CORS origins: {CORS_ORIGINS})")
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    from utils.logging_config import setup_logging
    setup_logging(log_level="INFO", json_format=False, console_output=True)

    host = os.getenv("API_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("API_SERVER_PORT", "5000"))
    run_api_server(host=host, port=port, debug=True)