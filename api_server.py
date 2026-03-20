#!/usr/bin/env python3
"""
API Server entry point for Hyperliquid Trading Bot Dashboard.
All routes are defined in the api/ package as Flask Blueprints.

Usage:
    python api_server.py
"""

import os
import secrets
import sys
from dotenv import load_dotenv

# LOAD .env ABSOLUTELY FIRST - before ANY other imports
load_dotenv()

# AUTO-GENERATE DASHBOARD_API_KEY if missing (fallback for first run)
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY")
if not DASHBOARD_API_KEY:
    DASHBOARD_API_KEY = secrets.token_urlsafe(32)
    os.environ["DASHBOARD_API_KEY"] = DASHBOARD_API_KEY
    print("\n" + "="*70)
    print("🚀 DASHBOARD_API_KEY AUTO-GENERATED (add to .env):")
    print(f"   DASHBOARD_API_KEY={DASHBOARD_API_KEY}")
    print("   VITE_DASHBOARD_API_KEY=" + DASHBOARD_API_KEY + "  # For frontend .env")
    print("="*70 + "\n")

# NOW import everything else (config will see the key)
import logging
from api import create_app
from api.config import CORS_ORIGINS

from utils.logging_config import setup_logging
setup_logging(log_level="INFO", json_format=False, console_output=True)

logger = logging.getLogger(__name__)


def run_api_server(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    """Start the API server."""
    app = create_app()

    execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()

    # Debug: Print detected API key status
    from api.config import API_AUTH_KEY
    api_key_status = "SET ✓" if API_AUTH_KEY else "EMPTY ✗"
    logger.info(f"DASHBOARD_API_KEY status: {api_key_status} (length={len(API_AUTH_KEY) if API_AUTH_KEY else 0})")

    # Security checks (now key is always set)
    if host == "0.0.0.0":
        logger.warning(
            "API server binding to 0.0.0.0 — ensure a reverse proxy with TLS is in front "
            "for production deployments."
        )

    # Never use Flask debug mode in live trading
    if execution_mode == "live" and debug:
        logger.warning("Forcing debug=False because EXECUTION_MODE=live")
        debug = False

    logger.info(
        f"🚀 Starting API server on http://{host}:{port} "
        f"(mode={execution_mode}, debug={debug}, CORS: {CORS_ORIGINS})"
    )
    print(f"\n✅ API Server ready: http://{host}:{port}")
    print(f"   Test: curl -H 'X-API-Key: {API_AUTH_KEY}' http://{host}:{port}/api/health")
    print()

    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    host = os.getenv("API_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("API_SERVER_PORT", "5000"))
    execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()

    # Only enable debug in paper mode
    use_debug = execution_mode != "live"

    run_api_server(host=host, port=port, debug=use_debug)