"""
Shared helper functions for API routes.
"""

import logging
import re
from typing import Any, Optional

import requests

from api.config import HYPERLIQUID_BASE_URL
from utils.retry import retry_request

# Re-export from shared utils so routes can import from one place
from utils.file_io import read_json_file  # noqa: F401

logger = logging.getLogger(__name__)

# ─── Hyperliquid proxy ────────────────────────────────────────────────────────

def post_hyperliquid_info(payload: dict, timeout: int = 15) -> Optional[Any]:
    """POST to Hyperliquid /info endpoint. Returns parsed JSON or None."""

    def _do_request():
        return requests.post(f"{HYPERLIQUID_BASE_URL}/info", json=payload, timeout=timeout)

    try:
        response = retry_request(
            _do_request,
            max_attempts=3,
            initial_delay=1.0,
            max_delay=8.0,
            backoff_factor=2.0,
            jitter=True,
            logger_instance=logger,
        )
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

SENSITIVE_REPLACEMENTS = [
    (re.compile(r'(?i)\b(?:private[_-]?key|secret|mnemonic)\s*[:=]\s*["\']?[^"\',\s]+["\']?'), '[REDACTED_SECRET_FIELD]'),
    (re.compile(r'\b0x[a-fA-F0-9]{64}\b'), '[REDACTED_PRIVATE_KEY]'),
    (re.compile(r'(?<![A-Za-z0-9])(?:[a-fA-F0-9]{64})(?![A-Za-z0-9])'), '[REDACTED_HEX_SECRET]'),
    (re.compile(r'\b0x[a-fA-F0-9]{40}\b'), '[REDACTED_WALLET]'),
    (re.compile(r'\bsk-or-[A-Za-z0-9_-]{16,}\b'), '[REDACTED_OPENROUTER_KEY]'),
    (re.compile(r'(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*'), 'Bearer [REDACTED_TOKEN]'),
    (re.compile(r'\b\d{8,}:[A-Za-z0-9_-]{20,}\b'), '[REDACTED_BOT_TOKEN]'),
    (re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'), '[REDACTED_ACCESS_KEY]'),
    (re.compile(r'\b[a-zA-Z0-9_]{6,}\.\.\.[a-zA-Z0-9_]{3,}\b'), '[REDACTED_PARTIAL_SECRET]'),
    (re.compile(r'"(private_key|api_key|wallet|token|secret)"\s*:\s*"[^"]*"', re.IGNORECASE), r'"\1":"[REDACTED]"'),
]


def sanitize_log_message(message: str) -> str:
    """Redact sensitive patterns from log messages before serving to dashboard."""
    if not isinstance(message, str):
        message = str(message)

    sanitized = message
    for pattern, replacement in SENSITIVE_REPLACEMENTS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized