"""
Shared helper functions for API routes.
"""

import logging
import re
from typing import Any, Dict, Optional

import requests

from api.config import HYPERLIQUID_BASE_URL

# Re-export from shared utils so routes can import from one place
from utils.file_io import read_json_file  # noqa: F401

logger = logging.getLogger(__name__)

# ─── Hyperliquid proxy ────────────────────────────────────────────────────────

def post_hyperliquid_info(payload: dict, timeout: int = 15) -> Optional[Any]:
    """POST to Hyperliquid /info endpoint. Returns parsed JSON or None."""
    try:
        response = requests.post(f"{HYPERLIQUID_BASE_URL}/info", json=payload, timeout=timeout)
        if response.status_code != 200:
            logger.error(f"Hyperliquid /info error: status={response.status_code}, type={payload.get('type', 'unknown')}")
            return None
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Hyperliquid /info timeout for type={payload.get('type', 'unknown')}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Hyperliquid /info connection error: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Hyperliquid /info request error: {e}")
        return None


# ─── Log sanitization ─────────────────────────────────────────────────────────

# Expanded patterns to cover more sensitive data formats
_SENSITIVE_PATTERNS = [
    # Ethereum private keys (64 hex chars, with or without 0x)
    (re.compile(r'\b(0x)?[0-9a-fA-F]{64}\b'), '[REDACTED_PRIVATE_KEY]'),
    # Wallet addresses (42 hex chars starting with 0x)
    (re.compile(r'\b0x[0-9a-fA-F]{40}\b'), '[REDACTED_WALLET]'),
    # API keys (sk-or- pattern for OpenRouter)
    (re.compile(r'\bsk-or-[A-Za-z0-9_-]{20,}\b'), '[REDACTED_OPENROUTER_KEY]'),
    # Generic API keys (long alphanumeric strings)
    (re.compile(r'\b[A-Za-z0-9_-]{32,}\b'), '[REDACTED_API_KEY]'),
    # Bearer tokens
    (re.compile(r'\bBearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), 'Bearer [REDACTED_TOKEN]'),
    # Telegram bot tokens (numeric:alphanumeric)
    (re.compile(r'\b\d{8,}:[A-Za-z0-9_-]{30,}\b'), '[REDACTED_BOT_TOKEN]'),
    # Partial key exposures (first/last parts)
    (re.compile(r'\b[0-9a-fA-F]{8,16}\.\.\.[0-9a-fA-F]{4,8}\b'), '[REDACTED_PARTIAL_KEY]'),
    # LLM responses containing potential sensitive data
    (re.compile(r'"(?:private_key|api_key|wallet|token)"\s*:\s*"[^"]*"', re.IGNORECASE), '"$1": "[REDACTED]"'),
]


def sanitize_log_message(message: str) -> str:
    """Redact sensitive patterns from log messages before serving to dashboard."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message