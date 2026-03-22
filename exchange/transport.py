import logging
from typing import Any, Dict, Optional

import requests

from utils.circuit_breaker import CircuitBreakerOpenError
from utils.retry import RETRYABLE_STATUS_CODES, retry_request

logger = logging.getLogger(__name__)


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
            logger.error(f"{endpoint_label} failed status={response.status_code}")
            response.raise_for_status()
        return response.json()

    try:
        return circuit_breaker.call(_do_post)
    except CircuitBreakerOpenError:
        logger.error(f"Circuit breaker OPEN for {endpoint_label}")
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
            logger.error(f"{endpoint_label} failed status={response.status_code}")
            response.raise_for_status()
        return response.json()

    try:
        return circuit_breaker.call(_do_post)
    except CircuitBreakerOpenError:
        logger.error(f"Circuit breaker OPEN for {endpoint_label}")
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