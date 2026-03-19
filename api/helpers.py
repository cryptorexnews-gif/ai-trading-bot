"""
Shared helper functions for API routes.
"""

import re
from typing import Any, Dict, Optional

import requests

from api.config import HYPERLIQUID_BASE_URL

# Re-export from shared utils so routes can import from one place
from utils.file_io import read_json_file  # noqa: F401


# ─── Hyperliquid proxy ────────────────────────────────────────────────────────

def post_hyperliquid_info(payload: dict, timeout: int = 15) -> Optional[Any]:
    """POST to Hyperliquid /info endpoint. Returns parsed JSON or None."""
    try:
        response = requests.post(
            f"{HYPERLIQUID_BASE_URL}/info",
            json=payload,
            timeout=timeout
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
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
]


def sanitize_log_message(message: str) -> str:
    """Redact sensitive patterns from log messages before serving to dashboard."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message