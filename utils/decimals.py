from decimal import Decimal
from typing import Any, Optional


def to_decimal(value: Any, default: Optional[Decimal] = None) -> Decimal:
    """
    Convert any value to Decimal with proper error handling.
    Returns default if conversion fails, or Decimal(0) if no default.
    """
    if value is None:
        return default if default is not None else Decimal("0")
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return default if default is not None else Decimal("0")


def to_int(value: Any, default: Optional[int] = None) -> int:
    """
    Convert to int with proper error handling.
    """
    if value is None:
        return default if default is not None else 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return default if default is not None else 0


def normalize_decimal(value: Decimal) -> Decimal:
    """
    Normalize a Decimal to remove trailing zeros and scientific notation.
    Useful for consistent serialization and comparison.
    """
    return value.normalize() if value is not None else Decimal("0")


def quantize_price(price: Decimal, tick_size: Decimal) -> Decimal:
    """
    Round price to the nearest tick size.
    """
    if tick_size <= 0:
        return price
    return (price / tick_size).quantize(Decimal("1")) * tick_size


def quantize_with_precision(value: Decimal, precision: int) -> Decimal:
    """
    Round value to a specific number of decimal places.
    """
    if precision < 0:
        return value
    quantizer = Decimal("1").scaleb(-precision)
    return value.quantize(quantizer)


def calculate_margin(size: Decimal, price: Decimal, leverage: Decimal) -> Decimal:
    """
    Calculate required margin for a position.
    """
    if leverage <= 0:
        return Decimal("0")
    return (size * price) / leverage


def calculate_position_value(size: Decimal, price: Decimal) -> Decimal:
    """
    Calculate total position value (notional).
    """
    return abs(size * price)


def calculate_pnl_percentage(entry_price: Decimal, current_price: Decimal, is_long: bool) -> Decimal:
    """
    Calculate unrealized PnL percentage.
    """
    if entry_price == 0:
        return Decimal("0")
    if is_long:
        return (current_price - entry_price) / entry_price
    else:
        return (entry_price - current_price) / entry_price


def is_valid_price(price: Decimal, min_price: Decimal = Decimal("0")) -> bool:
    """
    Check if price is valid (positive and above minimum).
    """
    return price > min_price


def is_valid_size(size: Decimal, min_size: Decimal = Decimal("0")) -> bool:
    """
    Check if size is valid (positive and above minimum).
    """
    return size >= min_size


def clamp(value: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
    """
    Clamp a value between min and max.
    """
    return max(min_val, min(value, max_val))


def percentage_of(value: Decimal, percent: Decimal) -> Decimal:
    """
    Calculate percentage of a value.
    percent should be in decimal form (e.g., 0.05 for 5%).
    """
    return value * percent


def add_percentage(value: Decimal, percent: Decimal) -> Decimal:
    """
    Add percentage to a value.
    percent should be in decimal form (e.g., 0.05 for 5%).
    """
    return value * (Decimal("1") + percent)


def subtract_percentage(value: Decimal, percent: Decimal) -> Decimal:
    """
    Subtract percentage from a value.
    percent should be in decimal form (e.g., 0.05 for 5%).
    """
    return value * (Decimal("1") - percent)