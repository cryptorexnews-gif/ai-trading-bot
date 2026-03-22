import logging
from typing import Any, Dict, Optional

import requests

from utils.circuit_breaker import CircuitBreakerOpenError
from utils.hyperliquid_errors import (
    AuthenticationError,
    ExchangeRejectedError,
    RateLimitError,
    UpstreamServerError,
)
from utils.retry import RETRYABLE_STATUS_CODES, retry_request

logger = logging.getLogger(__name__)


def _raise_hyperliquid_http_error(status_code: int, endpoint_label: str) -> None:
    if status_code in (401, 403):
        raise AuthenticationError(f"{endpoint_label} auth error status={status_code}")
    if status_code == 429:
        raise RateLimitError(f"{endpoint_label} rate limited")
    if status_code >= 500:
        raise UpstreamServerError(f"{endpoint_label} upstream error status={status_code}")
    raise ExchangeRejectedError(f"{endpoint_label} rejected status={status_code}")


def post_json_with_circuit_breaker(
    session: requests.Session,
    url: str,
    payload: Dict[str, Any],
    timeout: int,
    circuit_breaker,
    endpoint_label: str,
) -> Optional[Any]:
    def _raw_post():
        return session.post(url, json=payload, timeout=timeout)

    def _do_post():
        response = retry_request(
            _raw_post,
            max_attempts=3,
            initial_delay=1.0,
            max_delay=8.0,
            backoff_factor=2.0,
            jitter=True,
            retryable_status_codes=RETRYABLE_STATUS_CODES,
            logger_instance=logger,
        )
        if response.status_code != 200:
            _raise_hyperliquid_http_error(response.status_code, endpoint_label)
        return response.json()

    try:
        return circuit_breaker.call(_do_post)
    except CircuitBreakerOpenError:
        logger.error(f"Circuit breaker OPEN for {endpoint_label}")
        return None
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
            _raise_hyperliquid_http_error(status_code, endpoint_label)
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
        logger.error(f"{endpoint_label} timeout after {timeout}s")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"{endpoint_label} connection error: {e}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"{endpoint_label} HTTP error: status={getattr(e.response, 'status_code', 'unknown')}")
        return None
    except Exception as e:
        logger.error(f"{endpoint_label} unexpected error: {type(e).__name__}: {str(e)}")
        return None


def post_exchange_with_circuit_breaker(
    session: requests.Session,
    url: str,
    payload: Dict[str, Any],
    timeout: int,
    circuit_breaker,
    endpoint_label: str = "/exchange",
) -> Optional[Any]:
    def _raw_post():
        return session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

    def _do_post():
        response = retry_request(
            _raw_post,
            max_attempts=3,
            initial_delay=1.0,
            max_delay=8.0,
            backoff_factor=2.0,
            jitter=True,
            retryable_status_codes=RETRYABLE_STATUS_CODES,
            logger_instance=logger,
        )
        if response.status_code != 200:
            _raise_hyperliquid_http_error(response.status_code, endpoint_label)
        return response.json()

    try:
        return circuit_breaker.call(_do_post)
    except CircuitBreakerOpenError:
        logger.error(f"Circuit breaker OPEN for {endpoint_label}")
        return None
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
            _raise_hyperliquid_http_error(status_code, endpoint_label)
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
        logger.error(f"{endpoint_label} timeout after {timeout}s")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"{endpoint_label} connection error: {e}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"{endpoint_label} HTTP error: status={getattr(e.response, 'status_code', 'unknown')}")
        return None
    except Exception as e:
        logger.error(f"{endpoint_label} unexpected error: {type(e).__name__}: {str(e)}")
        return None