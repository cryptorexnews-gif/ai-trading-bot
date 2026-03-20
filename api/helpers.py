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
        response = requests.post(
            f"{HYPERLIQUID_BASE_URL}/info",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )
        if response.status_code == 200:
            return response.json()
        logger.warning(f"Hyperliquid /info returned status {response.status_code} for {payload.get('type', 'unknown')}")
        return None
    except requests.exceptions.Timeout:
        logger.warning(f"Hyperliquid /info timeout for {payload.get('type', 'unknown')}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Hyperliquid /info connection error: {e}")
        return None
    except Exception as e:
        logger.warning(f"Hyperliquid /info error: {type(e).__name__}: {e}")
        return None


# ─── Log sanitization ─────────────────────────────────────────────────────────

_SENSITIVE_PATTERNS = [
    # Ethereum private keys (64 hex chars)
    (re.compile(r'(0x)?[0-9a-fA-F]{64}'), '[REDACTED_KEY]'),
    # Bearer tokens
    (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), 'Bearer [REDACTED]'),
    # API keys (sk-... pattern)
    (re.compile(r'(sk-[A-Za-z0-9]{20,})'), '[REDACTED_API_KEY]'),
    # Telegram bot tokens (numeric:alphanumeric)
    (re.compile(r'\d{8,}:[A-Za-z0-9_-]{30,}'), '[REDACTED_BOT_TOKEN]'),
    # Wallet addresses (0x + 40 hex chars)
    (re.compile(r'(0x[a-fA-F0-9]{40})'), '[REDACTED_WALLET]'),
    # Hyperliquid wallet addresses in logs
    (re.compile(r'Wallet:\s*0x[a-fA-F0-9]{40}'), 'Wallet: [REDACTED]'),
    # Private key references
    (re.compile(r'private_key[=:]\s*[^\s,]+'), 'private_key=[REDACTED]'),
    # API key in URLs
    (re.compile(r'api[_-]?key[=:][^&\s]+'), 'api_key=[REDACTED]'),
]


def sanitize_log_message(message: str) -> str:
    """Redact sensitive patterns from log messages before serving to dashboard."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitize sensitive data in dictionaries."""
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_dict(item) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, str):
            # Check if key indicates sensitive data
            sensitive_keys = {'key', 'token', 'secret', 'password', 'private', 'wallet', 'address'}
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = '[REDACTED]'
            else:
                sanitized[key] = sanitize_log_message(value)
        else:
            sanitized[key] = value
    
    return sanitized