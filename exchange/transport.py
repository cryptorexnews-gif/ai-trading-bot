import logging
from typing import Any, Callable, Dict, Optional

import requests

from utils.circuit_breaker import CircuitBreakerOpenError

logger = logging.getLogger(__name__)


def post_json_with_circuit_breaker(
    session: requests.Session,
    url: str,
    payload: Dict[str, Any],
    timeout: int,
    circuit_breaker,
    endpoint_label: str,
) -> Optional[Any]:
    def _do_post():
        response = session.post(url, json=payload, timeout=timeout)
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
    def _do_post():
        response = session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
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
    except Exception as e:
        logger.error(f"{endpoint_label} unexpected error: {type(e).__name__}: {str(e)}")
        return None