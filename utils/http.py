"""
Shared HTTP session factory with connection pooling and retry.
Used by exchange_client, technical_analyzer, and llm_engine.
"""

import requests


def create_robust_session(
    pool_connections: int = 10,
    pool_maxsize: int = 10,
    max_retries: int = 2,
    backoff_factor: float = 0.3,
    status_forcelist: tuple = (502, 503, 504),
    content_type: str = "application/json"
) -> requests.Session:
    """
    Create a requests session with connection pooling and retry adapter.
    Shared across exchange client, data fetcher, and LLM engine.
    """
    session = requests.Session()
    if content_type:
        session.headers.update({"Content-Type": content_type})

    adapter = requests.adapters.HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=requests.adapters.Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=list(status_forcelist),
            allowed_methods=["POST"],
        ),
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session