import logging
import random
import time
from typing import Callable, Dict, List, Optional, Tuple, TypeVar

import requests

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration
DEFAULT_RETRY_CONFIG = {
    "max_attempts": 3,
    "initial_delay": 1.0,
    "max_delay": 60.0,
    "backoff_factor": 2.0,
    "jitter": True,
    "retry_on_status_codes": [429, 500, 502, 503, 504],
    "retry_on_exceptions": [
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError,
    ]
}


class RetryableHTTPError(Exception):
    """Custom exception for retryable HTTP errors."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


def should_retry_response(response: requests.Response) -> bool:
    """
    Determine if a response should trigger a retry.
    """
    if response.status_code in DEFAULT_RETRY_CONFIG["retry_on_status_codes"]:
        return True
    return False


def should_retry_exception(exception: Exception) -> bool:
    """
    Determine if an exception should trigger a retry.
    """
    for exc_type in DEFAULT_RETRY_CONFIG["retry_on_exceptions"]:
        if isinstance(exception, exc_type):
            return True
    return False


def calculate_backoff(attempt: int, config: Dict) -> float:
    """
    Calculate backoff delay for a given attempt.
    Includes jitter to avoid thundering herd.
    """
    delay = min(
        config["initial_delay"] * (config["backoff_factor"] ** attempt),
        config["max_delay"]
    )
    if config["jitter"]:
        # Add jitter: random value between 0.5 * delay and 1.5 * delay
        delay = delay * (0.5 + random.random())
    return delay


def retry_http(
    func: Callable[..., T],
    *args,
    config: Optional[Dict] = None,
    logger_instance: Optional[logging.Logger] = None,
    **kwargs
) -> T:
    """
    Retry an HTTP function with exponential backoff.
    
    Args:
        func: Function to retry (should return requests.Response or raise)
        *args: Arguments to pass to func
        config: Retry configuration (uses DEFAULT_RETRY_CONFIG if None)
        logger_instance: Logger to use (uses module logger if None)
        **kwargs: Keyword arguments to pass to func
        
    Returns:
        Result of successful function call
        
    Raises:
        Last exception if all retries fail
    """
    if config is None:
        config = DEFAULT_RETRY_CONFIG
    if logger_instance is None:
        logger_instance = logger
    
    last_exception = None
    last_response = None
    
    for attempt in range(config["max_attempts"]):
        try:
            response = func(*args, **kwargs)
            
            # If we got a response, check if it's retryable
            if isinstance(response, requests.Response):
                last_response = response
                if should_retry_response(response):
                    if attempt < config["max_attempts"] - 1:
                        delay = calculate_backoff(attempt, config)
                        logger_instance.warning(
                            f"Retryable HTTP {response.status_code} on attempt {attempt + 1}/{config['max_attempts']}. "
                            f"Retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        raise RetryableHTTPError(
                            response.status_code,
                            f"Max retries ({config['max_attempts']}) exceeded for HTTP {response.status_code}"
                        )
                return response
            return response
            
        except Exception as e:
            last_exception = e
            if should_retry_exception(e):
                if attempt < config["max_attempts"] - 1:
                    delay = calculate_backoff(attempt, config)
                    logger_instance.warning(
                        f"Retryable exception {type(e).__name__}: {str(e)} on attempt {attempt + 1}/{config['max_attempts']}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger_instance.error(
                        f"Max retries ({config['max_attempts']}) exceeded for exception {type(e).__name__}: {str(e)}"
                    )
            # If not retryable or max retries reached, re-raise
            raise
    
    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    if last_response:
        raise RetryableHTTPError(
            last_response.status_code,
            f"Max retries exceeded without successful response"
        )
    raise RuntimeError("Retry logic completed without result or exception")