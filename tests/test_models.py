"""
Test unitari per models.py — SL/TP/Trailing/Break-Even.
"""

import time
from decimal import Decimal

from models import (
    BreakEvenConfig,
    ManagedPosition,
    PortfolioState,
    PositionSide,
    StopLossConfig,
    TakeProfitConfig,
    TrailingStopConfig,
    TradingAction,
)


# ─── StopLossConfig ──────────────────────────────────────────────────────────

def test_stop_loss_long():
    sl = StopLossConfig(enabled=True, percentage=Decimal("0.03"))
    price = sl.calculate_stop_price(Decimal("100"), is_long=True)
    assert price == Decimal("97.00"), f"Expected 97.00, got {price}"


def test_stop_loss_short():
    sl = StopLossConfig(enabled=True, percentage=Decimal("0.03"))
    price = sl.calculate_stop_price(Decimal("100"), is_long=False)
    assert price == Decimal("103.00"), f"Expected 103.00, got {price}"


def test_stop_loss_absolute_price():
    sl = StopLossConfig(enabled=True, percentage=Decimal("0.03"), price=Decimal("95"))
    price = sl.calculate_stop_price(Decimal("100"), is_long=True)
    assert price == Decimal("95"), f"Absolute price should override percentage"


# ─── TakeProfitConfig ────────────────────────────────────────────────────────

def test_take_profit_long():
    tp = TakeProfitConfig(enabled=True, percentage=Decimal("0.05"))
    price = tp.calculate_tp_price(Decimal("100"), is_long=True)
    assert price == Decimal("105.00"), f"Expected 105.00, got {price}"


def test_take_profit_short():
    tp = TakeProfitConfig(enabled=True, percentage=Decimal("0.05"))
    price = tp.calculate_tp_price(Decimal("100"), is_long=False)
    assert price == Decimal("95.00"), f"Expected 95.00, got {price}"


# ─── TrailingStopConfig ──────────────────────────────────────────────────────

def test_trailing_stop_update_extreme_long():
    ts = TrailingStopConfig(enabled=True, callback_rate=Decimal("0.02"))
    ts.update_extreme(Decimal("105"), is_long=True)
    assert ts.highest_price == Decimal("105")
    ts.update_extreme(Decimal("110"), is_long=True)
    assert ts.highest_price == Decimal("110")
    ts.update_extreme(Decimal("108"), is_long=True)
    assert ts.highest_price == Decimal("110"), "Should not decrease"


def test_trailing_stop_trigger_long():
    ts = TrailingStopConfig(enabled=True, callback_rate=Decimal("0.02"))
    ts.highest_price = Decimal("110")
    # Trailing stop at 110 * 0.98 = 107.8
    assert ts.should_trigger(Decimal("107"), is_long=True) is True
    assert ts.should_trigger(Decimal("108"), is_long=True) is False


def test_trailing_stop_trigger_short():
    ts = TrailingStopConfig(enabled=True, callback_rate=Decimal("0.02"))
    ts.lowest_price = Decimal("90")
    # Trailing stop at 90 * 1.02 = 91.8
    assert ts.should_trigger(Decimal("92"), is_long=False) is True
    assert ts.should_trigger(Decimal("91"), is_long=False) is False


def test_trailing_stop_activation_price():
    ts = TrailingStopConfig(
        enabled=True, callback_rate=Decimal("0.02"),
        activation_price=Decimal("105")
    )
    ts.highest_price = Decimal("110")
    # Below activation price — should NOT trigger even if below trailing
    assert ts.should_trigger(Decimal("104"), is_long=True) is False
    # Above activation price and below trailing stop
    assert ts.should_trigger(Decimal("107"), is_long=True) is True


# ─── BreakEvenConfig ─────────────────────────────────────────────────────────

def test_break_even_should_activate_long():
    be = BreakEvenConfig(enabled=True, activation_pct=Decimal("0.015"))
    # +2% profit — should activate
    assert be.should_activate(Decimal("100"), Decimal("102"), is_long=True) is True
    # +1% profit — should NOT activate
    assert be.should_activate(Decimal("100"), Decimal("101"), is_long=True) is False


def test_break_even_should_activate_short():
    be = BreakEvenConfig(enabled=True, activation_pct=Decimal("0.015"))
    # +2% profit on short (price dropped)
    assert be.should_activate(Decimal("100"), Decimal("98"), is_long=False) is True
    # +1% profit — should NOT activate
    assert be.should_activate(Decimal("100"), Decimal("99"), is_long=False) is False


def test_break_even_already_activated():
    be = BreakEvenConfig(enabled=True, activation_pct=Decimal("0.015"), activated=True)
    assert be.should_activate(Decimal("100"), Decimal("110"), is_long=True) is False


def test_break_even_price_long():
    be = BreakEvenConfig(enabled=True, offset_pct=Decimal("0.001"))
    price = be.get_break_even_price(Decimal("100"), is_long=True)
    assert price == Decimal("100.1"), f"Expected 100.1, got {price}"


def test_break_even_price_short():
    be = BreakEvenConfig(enabled=True, offset_pct=Decimal("0.001"))
    price = be.get_break_even_price(Decimal("100"), is_long=False)
    assert price == Decimal("99.9"), f"Expected 99.9, got {price}"


# ─── ManagedPosition ─────────────────────────────────────────────────────────

def test_managed_position_should_stop_loss():
    pos = ManagedPosition(
        coin="BTC", size=Decimal("0.1"), entry_price=Decimal("100"),
        is_long=True, leverage=5,
        stop_loss=StopLossConfig(enabled=True, percentage=Decimal("0.03")),
    )
    assert pos.should_stop_loss(Decimal("96")) is True
    assert pos.should_stop_loss(Decimal("98")) is False


def test_managed_position_should_take_profit():
    pos = ManagedPosition(
        coin="ETH", size=Decimal("1"), entry_price=Decimal("100"),
        is_long=True, leverage=3,
        take_profit=TakeProfitConfig(enabled=True, percentage=Decimal("0.05")),
    )
    assert pos.should_take_profit(Decimal("106")) is True
    assert pos.should_take_profit(Decimal("104")) is False


def test_managed_position_check_break_even():
    pos = ManagedPosition(
        coin="SOL", size=Decimal("10"), entry_price=Decimal("100"),
        is_long=True, leverage=5,
        stop_loss=StopLossConfig(enabled=True, percentage=Decimal("0.03")),
        break_even=BreakEvenConfig(
            enabled=True, activation_pct=Decimal("0.015"),
            offset_pct=Decimal("0.001")
        ),
    )
    # Not enough profit yet
    assert pos.check_break_even(Decimal("101")) is False
    assert pos.break_even.activated is False

    # Enough profit — should activate
    assert pos.check_break_even(Decimal("102")) is True
    assert pos.break_even.activated is True
    # SL should now be at entry + 0.1% = 100.1
    assert pos.stop_loss.price == Decimal("100.1")

    # Should not re-activate
    assert pos.check_break_even(Decimal("105")) is False


def test_managed_position_serialization():
    pos = ManagedPosition(
        coin="BTC", size=Decimal("0.5"), entry_price=Decimal("50000"),
        is_long=True, leverage=5, opened_at=1000.0,
        stop_loss=StopLossConfig(enabled=True, percentage=Decimal("0.02")),
        take_profit=TakeProfitConfig(enabled=True, percentage=Decimal("0.06")),
        trailing_stop=TrailingStopConfig(enabled=True, callback_rate=Decimal("0.015")),
        break_even=BreakEvenConfig(enabled=True, activation_pct=Decimal("0.02"), activated=True),
    )
    data = pos.to_dict()
    restored = ManagedPosition.from_dict(data)

    assert restored.coin == "BTC"
    assert restored.size == Decimal("0.5")
    assert restored.entry_price == Decimal("50000")
    assert restored.is_long is True
    assert restored.leverage == 5
    assert restored.stop_loss.percentage == Decimal("0.02")
    assert restored.take_profit.percentage == Decimal("0.06")
    assert restored.trailing_stop.callback_rate == Decimal("0.015")
    assert restored.break_even.activated is True


# ─── PortfolioState ───────────────────────────────────────────────────────────

def test_portfolio_state_position_side():
    ps = PortfolioState(
        total_balance=Decimal("1000"),
        available_balance=Decimal("500"),
        margin_usage=Decimal("0.5"),
        positions={
            "BTC": {"size": Decimal("0.1"), "entry_price": Decimal("50000"), "unrealized_pnl": Decimal("10")},
            "ETH": {"size": Decimal("-1"), "entry_price": Decimal("3000"), "unrealized_pnl": Decimal("-5")},
        }
    )
    assert ps.get_position_side("BTC") == PositionSide.LONG
    assert ps.get_position_side("ETH") == PositionSide.SHORT
    assert ps.get_position_side("SOL") == PositionSide.NONE


def test_portfolio_state_total_exposure():
    ps = PortfolioState(
        total_balance=Decimal("1000"),
        available_balance=Decimal("500"),
        margin_usage=Decimal("0.5"),
        positions={
            "BTC": {"size": Decimal("0.1"), "entry_price": Decimal("50000"), "unrealized_pnl": Decimal("0")},
        }
    )
    assert ps.get_total_exposure() == Decimal("5000")


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