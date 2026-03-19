from decimal import Decimal
from typing import Any, Optional


def to_decimal(value: Any, default: Optional[Decimal] = None) -> Decimal:
    """
    Converte qualsiasi valore in Decimal con gestione degli errori appropriata.
    Restituisce il valore predefinito se la conversione fallisce, o Decimal(0) se non è specificato.
    """
    if value is None:
        return default if default is not None else Decimal("0")
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return default if default is not None else Decimal("0")


def to_int(value: Any, default: Optional[int] = None) -> int:
    """
    Converte in int con gestione degli errori appropriata.
    """
    if value is None:
        return default if default is not None else 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return default if default is not None else 0


def normalize_decimal(value: Decimal) -> Decimal:
    """
    Normalizza un Decimal rimuovendo zeri finali e notazione scientifica.
    Utile per una serializzazione e confronto coerenti.
    """
    return value.normalize() if value is not None else Decimal("0")


def quantize_price(price: Decimal, tick_size: Decimal) -> Decimal:
    """
    Arrotonda il prezzo al tick size più vicino.
    """
    if tick_size <= 0:
        return price
    return (price / tick_size).quantize(Decimal("1")) * tick_size


def quantize_with_precision(value: Decimal, precision: int) -> Decimal:
    """
    Arrotonda il valore a un numero specifico di posizioni decimali.
    """
    if precision < 0:
        return value
    quantizer = Decimal("1").scaleb(-precision)
    return value.quantize(quantizer)


def calculate_margin(size: Decimal, price: Decimal, leverage: Decimal) -> Decimal:
    """
    Calcola il margine richiesto per una posizione.
    """
    if leverage <= 0:
        return Decimal("0")
    return (size * price) / leverage


def calculate_position_value(size: Decimal, price: Decimal) -> Decimal:
    """
    Calcola il valore totale della posizione (notionale).
    """
    return abs(size * price)


def calculate_pnl_percentage(entry_price: Decimal, current_price: Decimal, is_long: bool) -> Decimal:
    """
    Calcola la percentuale di PnL non realizzata.
    """
    if entry_price == 0:
        return Decimal("0")
    if is_long:
        return (current_price - entry_price) / entry_price
    else:
        return (entry_price - current_price) / entry_price


def is_valid_price(price: Decimal, min_price: Decimal = Decimal("0")) -> bool:
    """
    Verifica se il prezzo è valido (positivo e sopra il minimo).
    """
    return price > min_price


def is_valid_size(size: Decimal, min_size: Decimal = Decimal("0")) -> bool:
    """
    Verifica se la dimensione è valida (positiva e sopra il minimo).
    """
    return size >= min_size


def clamp(value: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    """
    Limita un valore tra min e max.
    """
    return max(min_val, min(value, max_val))


def percentage_of(value: Decimal, percent: Decimal) -> Decimal:
    """
    Calcola la percentuale di un valore.
    percent dovrebbe essere in forma decimale (es. 0.05 per 5%).
    """
    return value * percent


def add_percentage(value: Decimal, percent: Decimal) -> Decimal:
    """
    Aggiunge una percentuale a un valore.
    percent dovrebbe essere in forma decimale (es. 0.05 per 5%).
    """
    return value * (Decimal("1") + percent)


def subtract_percentage(value: Decimal, percent: Decimal) -> Decimal:
    """
    Sottrae una percentuale da un valore.
    percent dovrebbe essere in forma decimale (es. 0.05 per 5%).
    """
    return value * (Decimal("1") - percent)