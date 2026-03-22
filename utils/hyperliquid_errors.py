class HyperliquidAPIError(Exception):
    """Base exception for Hyperliquid API errors."""


class AuthenticationError(HyperliquidAPIError):
    """Authentication/authorization failed for Hyperliquid API."""


class RateLimitError(HyperliquidAPIError):
    """Hyperliquid API rate limit exceeded."""


class UpstreamServerError(HyperliquidAPIError):
    """Hyperliquid API upstream server error (5xx)."""


class ExchangeRejectedError(HyperliquidAPIError):
    """Hyperliquid exchange rejected the request."""