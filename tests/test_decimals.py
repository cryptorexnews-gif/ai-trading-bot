"""
Test unitari per utils/decimals.py — utilità aritmetiche Decimal.
"""

from decimal import Decimal

from utils.decimals import (
    safe_decimal,
    to_decimal,
    decimal_sqrt,
    clamp,
    percentage_of,
    add_percentage,
    subtract_percentage,
    calculate_margin,
    calculate_position_value,
    calculate_pnl_percentage,
    is_valid_price,
    is_valid_size,
    quantize_price,
)


# ─── safe_decimal / to_decimal ────────────────────────────────────────────────

def test_safe_decimal_from_string():
    assert safe_decimal("123.45") == Decimal("123.45")


def test_safe_decimal_from_int():
    assert safe_decimal(42) == Decimal("42")


def test_safe_decimal_from_float():
    result = safe_decimal(3.14)
    assert result == Decimal("3.14")


def test_safe_decimal_from_none():
    assert safe_decimal(None) == Decimal("0")


def test_safe_decimal_from_none_with_default():
    assert safe_decimal(None, Decimal("99")) == Decimal("99")


def test_safe_decimal_from_invalid():
    assert safe_decimal("not_a_number") == Decimal("0")


def test_safe_decimal_from_invalid_with_default():
    assert safe_decimal("abc", Decimal("42")) == Decimal("42")


# ─── decimal_sqrt ─────────────────────────────────────────────────────────────

def test_decimal_sqrt_perfect_square():
    result = decimal_sqrt(Decimal("4"))
    assert abs(result - Decimal("2")) < Decimal("0.0001"), f"sqrt(4) should be ~2, got {result}"


def test_decimal_sqrt_non_perfect():
    result = decimal_sqrt(Decimal("2"))
    assert abs(result - Decimal("1.4142")) < Decimal("0.001"), f"sqrt(2) should be ~1.4142, got {result}"


def test_decimal_sqrt_zero():
    assert decimal_sqrt(Decimal("0")) == Decimal("0")


def test_decimal_sqrt_negative():
    assert decimal_sqrt(Decimal("-1")) == Decimal("0")


def test_decimal_sqrt_large():
    result = decimal_sqrt(Decimal("1000000"))
    assert abs(result - Decimal("1000")) < Decimal("0.01"), f"sqrt(1000000) should be ~1000, got {result}"


# ─── clamp ────────────────────────────────────────────────────────────────────

def test_clamp_within_range():
    assert clamp(Decimal("5"), Decimal("0"), Decimal("10")) == Decimal("5")


def test_clamp_below_min():
    assert clamp(Decimal("-1"), Decimal("0"), Decimal("10")) == Decimal("0")


def test_clamp_above_max():
    assert clamp(Decimal("15"), Decimal("0"), Decimal("10")) == Decimal("10")


# ─── Percentages ──────────────────────────────────────────────────────────────

def test_percentage_of():
    assert percentage_of(Decimal("100"), Decimal("0.05")) == Decimal("5")


def test_add_percentage():
    assert add_percentage(Decimal("100"), Decimal("0.1")) == Decimal("110")


def test_subtract_percentage():
    assert subtract_percentage(Decimal("100"), Decimal("0.1")) == Decimal("90")


# ─── Financial calculations ───────────────────────────────────────────────────

def test_calculate_margin():
    margin = calculate_margin(Decimal("1"), Decimal("50000"), Decimal("10"))
    assert margin == Decimal("5000"), f"Expected 5000, got {margin}"


def test_calculate_margin_zero_leverage():
    assert calculate_margin(Decimal("1"), Decimal("50000"), Decimal("0")) == Decimal("0")


def test_calculate_position_value():
    value = calculate_position_value(Decimal("-0.5"), Decimal("50000"))
    assert value == Decimal("25000"), f"Expected 25000, got {value}"


def test_pnl_percentage_long():
    pnl = calculate_pnl_percentage(Decimal("100"), Decimal("110"), is_long=True)
    assert pnl == Decimal("0.1"), f"Expected 0.1, got {pnl}"


def test_pnl_percentage_short():
    pnl = calculate_pnl_percentage(Decimal("100"), Decimal("90"), is_long=False)
    assert pnl == Decimal("0.1"), f"Expected 0.1, got {pnl}"


def test_pnl_percentage_zero_entry():
    assert calculate_pnl_percentage(Decimal("0"), Decimal("100"), is_long=True) == Decimal("0")


# ─── Validation ───────────────────────────────────────────────────────────────

def test_is_valid_price():
    assert is_valid_price(Decimal("100")) is True
    assert is_valid_price(Decimal("0")) is False
    assert is_valid_price(Decimal("-1")) is False


def test_is_valid_size():
    assert is_valid_size(Decimal("1")) is True
    assert is_valid_size(Decimal("0")) is True
    assert is_valid_size(Decimal("-1")) is False


# ─── quantize_price ──────────────────────────────────────────────────────────

def test_quantize_price():
    result = quantize_price(Decimal("100.123"), Decimal("0.01"))
    assert result == Decimal("100.12") or result == Decimal("100.13"), f"Got {result}"


def test_quantize_price_zero_tick():
    result = quantize_price(Decimal("100.123"), Decimal("0"))
    assert result == Decimal("100.123"), "Zero tick should return original"


if __name__ == "__main__":
    import sys
    test_functions = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for test_fn in test_functions:
        try:
            test_fn()
            passed += 1
            print(f"  ✅ {test_fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {test_fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  💥 {test_fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(1 if failed > 0 else 0)