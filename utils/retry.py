import logging
import random
import time
from typing import Callable, Dict, List, Optional, Tuple, TypeVar

import requests

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Configurazione di retry predefinita
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
    """Eccezione personalizzata per errori HTTP retryable."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


def should_retry_response(response: requests.Response) -> bool:
    """
    Determina se una risposta dovrebbe attivare un retry.
    """
    if response.status_code in DEFAULT_RETRY_CONFIG["retry_on_status_codes"]:
        return True
    return False


def should_retry_exception(exception: Exception) -> bool:
    """
    Determina se un'eccezione dovrebbe attivare un retry.
    """
    for exc_type in DEFAULT_RETRY_CONFIG["retry_on_exceptions"]:
        if isinstance(exception, exc_type):
            return True
    return False


def calculate_backoff(attempt: int, config: Dict) -> float:
    """
    Calcola il ritardo di backoff per un tentativo specifico.
    Include jitter per evitare thundering herd.
    """
    delay = min(
        config["initial_delay"] * (config["backoff_factor"] ** attempt),
        config["max_delay"]
    )
    if config["jitter"]:
        # Aggiunge jitter: valore casuale tra 0.5 * delay e 1.5 * delay
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
    Riprova una funzione HTTP con backoff esponenziale.
    
    Args:
        func: Funzione da riprovare (dovrebbe restituire requests.Response o sollevare)
        *args: Argomenti da passare a func
        config: Configurazione di retry (usa DEFAULT_RETRY_CONFIG se None)
        logger_instance: Logger da usare (usa logger del modulo se None)
        **kwargs: Argomenti chiave da passare a func
        
    Returns:
        Risultato della chiamata di funzione riuscita
        
    Raises:
        Ultima eccezione se tutti i retry falliscono
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
            
            # Se abbiamo ricevuto una risposta, controlla se è retryable
            if isinstance(response, requests.Response):
                last_response = response
                if should_retry_response(response):
                    if attempt < config["max_attempts"] - 1:
                        delay = calculate_backoff(attempt, config)
                        logger_instance.warning(
                            f"Risposta retryable HTTP {response.status_code} al tentativo {attempt + 1}/{config['max_attempts']}. "
                            f"Riprovo tra {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        raise RetryableHTTPError(
                            response.status_code,
                            f"Massimo numero di tentativi ({config['max_attempts']}) superato per HTTP {response.status_code}"
                        )
                return response
            return response
            
        except Exception as e:
            last_exception = e
            if should_retry_exception(e):
                if attempt < config["max_attempts"] - 1:
                    delay = calculate_backoff(attempt, config)
                    logger_instance.warning(
                        f"Eccezione retryable {type(e).__name__}: {str(e)} al tentativo {attempt + 1}/{config['max_attempts']}. "
                        f"Riprovo tra {delay:.2f}s"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger_instance.error(
                        f"Massimo numero di tentativi ({config['max_attempts']}) superato per eccezione {type(e).__name__}: {str(e)}"
                    )
            # Se non è retryable o massimo tentativi raggiunto, rilancia
            raise
    
    # Non dovrebbe raggiungere qui, ma per sicurezza
    if last_exception:
        raise last_exception
    if last_response:
        raise RetryableHTTPError(
            last_response.status_code,
            f"Massimo numero di tentativi superato senza risposta riuscita"
        )
    raise RuntimeError("Logica di retry completata senza risultato o eccezione")