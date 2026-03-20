import logging
import random
import time
from typing import Callable, Optional, Set, TypeVar

import requests

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS_CODES: Set[int] = {429, 500, 502, 503, 504}

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)


def calculate_backoff(
    attempt: int,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True
) -> float:
    """
    Calcola il ritardo di backoff per un tentativo specifico.
    Include jitter per evitare thundering herd.
    """
    delay = min(initial_delay * (backoff_factor ** attempt), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random())
    return delay


def retry_request(
    func: Callable[..., T],
    *args,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_status_codes: Optional[Set[int]] = None,
    logger_instance: Optional[logging.Logger] = None,
    **kwargs
) -> T:
    """
    Riprova una funzione con backoff esponenziale.
    Gestisce sia eccezioni di rete che risposte HTTP con status retryable.

    Args:
        func: Funzione da riprovare
        max_attempts: Numero massimo di tentativi
        initial_delay: Ritardo iniziale in secondi
        max_delay: Ritardo massimo in secondi
        backoff_factor: Fattore di moltiplicazione per backoff
        jitter: Se aggiungere jitter casuale
        retryable_status_codes: Set di status code HTTP da riprovare
        logger_instance: Logger da usare

    Returns:
        Risultato della chiamata di funzione riuscita

    Raises:
        Ultima eccezione se tutti i retry falliscono
    """
    if retryable_status_codes is None:
        retryable_status_codes = RETRYABLE_STATUS_CODES
    if logger_instance is None:
        logger_instance = logger

    last_exception = None

    for attempt in range(max_attempts):
        try:
            result = func(*args, **kwargs)

            # Se il risultato è una Response, controlla status code
            if isinstance(result, requests.Response):
                if result.status_code in retryable_status_codes:
                    if attempt < max_attempts - 1:
                        delay = calculate_backoff(attempt, initial_delay, max_delay, backoff_factor, jitter)
                        logger_instance.warning(
                            f"HTTP {result.status_code} al tentativo {attempt + 1}/{max_attempts}. "
                            f"Riprovo tra {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        # Ultimo tentativo, solleva eccezione
                        result.raise_for_status()

            return result

        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e
            if attempt < max_attempts - 1:
                delay = calculate_backoff(attempt, initial_delay, max_delay, backoff_factor, jitter)
                logger_instance.warning(
                    f"{type(e).__name__} al tentativo {attempt + 1}/{max_attempts}. "
                    f"Riprovo tra {delay:.2f}s"
                )
                time.sleep(delay)
                continue
            else:
                logger_instance.error(
                    f"Tutti i {max_attempts} tentativi falliti. "
                    f"Ultimo errore: {type(e).__name__}: {str(e)}"
                )
                raise

        except Exception:
            # Eccezioni non retryable — rilancia immediatamente
            raise

    # Non dovrebbe raggiungere qui
    if last_exception:
        raise last_exception
    raise RuntimeError("Logica di retry completata senza risultato o eccezione")