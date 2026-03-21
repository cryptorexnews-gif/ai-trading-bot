"""
API server configuration — paths, env vars, constants.
Validates CORS origins at import time.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

# Security: Dashboard API key
API_AUTH_KEY = os.getenv("DASHBOARD_API_KEY", "")

# Security: CORS origins — validated
_raw_cors = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
)

_ORIGIN_PATTERN = re.compile(r'^https?://[a-zA-Z0-9\-.:]+$')


def _validate_cors_origins(raw: str) -> list:
    """Parse and validate CORS origins. Rejects wildcard in live mode."""
    execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()
    origins = [o.strip() for o in raw.split(",") if o.strip()]

    validated = []
    for origin in origins:
        if origin == "*":
            if execution_mode == "live":
                logger.error(
                    "SECURITY: CORS_ALLOWED_ORIGINS='*' is forbidden when EXECUTION_MODE=live. "
                    "Falling back to localhost only."
                )
                return ["http://localhost:3000", "http://127.0.0.1:3000"]
            else:
                logger.warning(
                    "SECURITY WARNING: CORS_ALLOWED_ORIGINS='*' allows any origin. "
                    "This is only acceptable in development."
                )
                validated.append(origin)
        elif _ORIGIN_PATTERN.match(origin):
            validated.append(origin)
        else:
            logger.warning(f"CORS: Ignoring invalid origin format: '{origin}'")

    if not validated:
        logger.warning("CORS: No valid origins configured, defaulting to localhost")
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

    return validated


CORS_ORIGINS = _validate_cors_origins(_raw_cors)

# Security headers
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

# State file paths
STATE_PATH = "state/bot_state.json"
METRICS_PATH = "state/bot_metrics.json"
LIVE_STATUS_PATH = "state/bot_live_status.json"
MANAGED_POSITIONS_PATH = "state/managed_positions.json"
RUNTIME_CONFIG_PATH = "state/runtime_config.json"

# Hyperliquid API
HYPERLIQUID_BASE_URL = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")

# Log file
LOG_FILE = os.getenv("LOG_FILE", "logs/hyperliquid_bot.log")

# Valid coin pattern for input validation
COIN_PATTERN = re.compile(r'^[A-Z0-9]{1,20}$')

# Known trading pairs (loaded from env or defaults)
_pairs_raw = os.getenv(
    "TRADING_PAIRS",
    "BTC,ETH,SOL,BNB,ADA,DOGE,XRP,AVAX,LINK,SUI,ARB,OP,NEAR,WIF,PEPE,INJ,TIA,SEI,RENDER,FET"
)
KNOWN_TRADING_PAIRS = {p.strip().upper() for p in _pairs_raw.split(",") if p.strip()}
KNOWN_TRADING_PAIRS.add("BTC")