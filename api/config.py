"""
API server configuration — paths, env vars, constants.
"""

import os

# Security: CORS origins
CORS_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

# Security: Dashboard API key
API_AUTH_KEY = os.getenv("DASHBOARD_API_KEY", "")

# State file paths
STATE_PATH = "state/bot_state.json"
METRICS_PATH = "state/bot_metrics.json"
LIVE_STATUS_PATH = "state/bot_live_status.json"
MANAGED_POSITIONS_PATH = "state/managed_positions.json"

# Hyperliquid API
HYPERLIQUID_BASE_URL = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")

# Log file
LOG_FILE = os.getenv("LOG_FILE", "logs/hyperliquid_bot.log")