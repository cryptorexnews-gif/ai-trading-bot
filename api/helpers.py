"""
Shared helper functions for API routes.
"""

from typing import Any, Optional

from api.services.hyperliquid_proxy_service import post_hyperliquid_info as _post_hyperliquid_info
from api.services.log_sanitizer_service import sanitize_log_message as _sanitize_log_message

# Re-export from shared utils so routes can import from one place
from utils.file_io import read_json_file  # noqa: F401


def post_hyperliquid_info(payload: dict, timeout: int = 15) -> Optional[Any]:
    """POST to Hyperliquid /info endpoint. Returns parsed JSON or None."""
    return _post_hyperliquid_info(payload=payload, timeout=timeout)


def sanitize_log_message(message: str) -> str:
    """Redact sensitive patterns from log messages before serving to dashboard."""
    return _sanitize_log_message(message)