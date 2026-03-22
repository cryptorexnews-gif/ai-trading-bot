import logging
from typing import Any, Optional

import requests

from api.config import HYPERLIQUID_BASE_URL
from utils.hyperliquid_errors import (
    AuthenticationError,
    ExchangeRejectedError,
    HyperliquidAPIError,
    RateLimitError,
    UpstreamServerError,
)
from utils.retry import retry_request

logger = logging.getLogger(__name__)


def raise_hyperliquid_http_error(status_code: int, endpoint_type: str) -> None:
    if status_code in (401, 403):
        raise AuthenticationError(f"hyperliquid_auth_error type={endpoint_type} status={status_code}")
    if status_code == 429:
        raise RateLimitError(f"hyperliquid_rate_limited type={endpoint_type}")
    if status_code >= 500:
        raise UpstreamServerError(f"hyperliquid_upstream_error type={endpoint_type} status={status_code}")
    raise ExchangeRejectedError(f"hyperliquid_request_rejected type={endpoint_type} status={status_code}")


def post_hyperliquid_info(payload: dict, timeout: int = 15) -> Optional[Any]:
    endpoint_type = payload.get("type", "unknown")

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
            raise_hyperliquid_http_error(response.status_code, endpoint_type)
        return response.json()
    except AuthenticationError as e:
        logger.error(str(e))
        return None
    except RateLimitError as e:
        logger.warning(str(e))
        return None
    except UpstreamServerError as e:
        logger.error(str(e))
        return None
    except ExchangeRejectedError as e:
        logger.error(str(e))
        return None
    except requests.exceptions.HTTPError as e:
        status_code = getattr(e.response, "status_code", 0) or 0
        try:
            raise_hyperliquid_http_error(status_code, endpoint_type)
        except AuthenticationError as mapped:
            logger.error(str(mapped))
        except RateLimitError as mapped:
            logger.warning(str(mapped))
        except UpstreamServerError as mapped:
            logger.error(str(mapped))
        except ExchangeRejectedError as mapped:
            logger.error(str(mapped))
        return None
    except requests.exceptions.Timeout:
        logger.error(f"Hyperliquid /info timeout for type={endpoint_type}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Hyperliquid /info connection error: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Hyperliquid /info request error: {e}")
        return None
    except HyperliquidAPIError as e:
        logger.error(f"Hyperliquid API error: {e}")
        return None