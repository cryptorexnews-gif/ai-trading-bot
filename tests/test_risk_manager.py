"""
Test unitari per risk_manager.py — validazione ordini e protezione rischio.
"""

import time
from decimal import Decimal

from models import PortfolioState, TradingAction
from risk_manager import RiskManager


def _make_risk_manager(**overrides) -> RiskManager:
    defaults = {
        "min_size_by_coin": {"BTC": Decimal("0.001"), "ETH": Decimal("0.01"), "SOL": Decimal("0.1")},
        "hard_max_leverage": Decimal("10"),
        "min_confidence_open": Decimal("0.72"),
        "min_confidence_manage": Decimal("0.50"),
        "max_margin_usage": Decimal("0.8"),
        "max_order_margin_pct": Decimal("0.1"),
        "trade_cooldown_sec": 300,
        "daily_notional_limit_usd": Decimal("1000"),
        "volatility_multiplier": Decimal("1.2"),
        "max_drawdown_pct": Decimal("0.15"),
        "max_single_asset_pct": Decimal("0.35"),
        "emergency_margin_threshold": Decimal("0.88"),
    }
    defaults.update(overrides)
    return RiskManager(**defaults)


def _make_portfolio(balance="1000", available="500", margin_usage="0.3", positions=None) -> PortfolioState:
    return PortfolioState(
        total_balance=Decimal(balance),
        available_balance=Decimal(available),
        margin_usage=Decimal(margin_usage),
        positions=positions or {},
    )


# ─── Hold always passes ──────────────────────────────────────────────────────

def test_hold_always_passes():
    rm = _make_risk_manager()
    ps = _make_portfolio()
    order = {"action": "hold", "size": 0, "leverage": 1, "confidence": 0.0}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is True
    assert reason == "hold"


# ─── Unknown action rejected ─────────────────────────────────────────────────

def test_unknown_action_rejected():
    rm = _make_risk_manager()
    ps = _make_portfolio()
    order = {"action": "yolo", "size": 1, "leverage": 1, "confidence": 0.9}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "unknown_action"


# ─── Leverage bounds ──────────────────────────────────────────────────────────

def test_leverage_too_high():
    rm = _make_risk_manager()
    ps = _make_portfolio()
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 20, "confidence": 0.9}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "leverage_out_of_bounds"


def test_leverage_zero():
    rm = _make_risk_manager()
    ps = _make_portfolio()
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 0, "confidence": 0.9}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "leverage_out_of_bounds"


# ─── Confidence thresholds ────────────────────────────────────────────────────

def test_confidence_too_low_for_open():
    rm = _make_risk_manager()
    ps = _make_portfolio()
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.5}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "confidence_open_too_low"


def test_confidence_ok_for_manage():
    rm = _make_risk_manager()
    ps = _make_portfolio(positions={"BTC": {"size": Decimal("0.1"), "entry_price": Decimal("50000"), "unrealized_pnl": Decimal("0"), "margin_used": Decimal("100")}})
    order = {"action": "close_position", "size": Decimal("0.1"), "leverage": 1, "confidence": 0.55}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is True


def test_confidence_too_low_for_manage():
    rm = _make_risk_manager()
    ps = _make_portfolio()
    order = {"action": "close_position", "size": Decimal("0.1"), "leverage": 1, "confidence": 0.3}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "confidence_manage_too_low"


# ─── Drawdown protection ─────────────────────────────────────────────────────

def test_drawdown_breached():
    rm = _make_risk_manager()
    ps = _make_portfolio(balance="800")
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    ok, reason = rm.check_order(
        "BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time(),
        peak_portfolio_value=Decimal("1000")
    )
    assert ok is False
    assert reason == "max_drawdown_breached"


def test_drawdown_ok():
    rm = _make_risk_manager()
    ps = _make_portfolio(balance="950")
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    ok, reason = rm.check_order(
        "BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time(),
        peak_portfolio_value=Decimal("1000")
    )
    assert ok is True


# ─── Margin usage ─────────────────────────────────────────────────────────────

def test_margin_usage_too_high():
    rm = _make_risk_manager()
    ps = _make_portfolio(margin_usage="0.85")
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "margin_usage_too_high"


# ─── Position conflict ────────────────────────────────────────────────────────

def test_conflict_buy_while_short():
    rm = _make_risk_manager()
    ps = _make_portfolio(positions={"BTC": {"size": Decimal("-0.1"), "entry_price": Decimal("50000"), "unrealized_pnl": Decimal("0"), "margin_used": Decimal("100")}})
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "conflict_buy_while_short"


def test_conflict_sell_while_long():
    rm = _make_risk_manager()
    ps = _make_portfolio(positions={"BTC": {"size": Decimal("0.1"), "entry_price": Decimal("50000"), "unrealized_pnl": Decimal("0"), "margin_used": Decimal("100")}})
    order = {"action": "sell", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "conflict_sell_while_long"


# ─── Cooldown ─────────────────────────────────────────────────────────────────

def test_cooldown_active():
    rm = _make_risk_manager(trade_cooldown_sec=300)
    ps = _make_portfolio()
    now = time.time()
    last_trades = {"BTC": now - 100}  # 100 seconds ago, cooldown is 300
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, last_trades, Decimal("0"), now)
    assert ok is False
    assert reason == "cooldown_active"


def test_cooldown_expired():
    rm = _make_risk_manager(trade_cooldown_sec=300)
    ps = _make_portfolio()
    now = time.time()
    last_trades = {"BTC": now - 400}  # 400 seconds ago, cooldown is 300
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, last_trades, Decimal("0"), now)
    assert ok is True


# ─── Daily notional cap ──────────────────────────────────────────────────────

def test_daily_notional_cap_exceeded():
    rm = _make_risk_manager(daily_notional_limit_usd=Decimal("500"))
    ps = _make_portfolio()
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    ok, reason = rm.check_order(
        "BTC", order, Decimal("50000"), ps, {}, Decimal("490"), time.time()
    )
    assert ok is False
    assert reason == "daily_notional_cap_exceeded"


# ─── Emergency derisk ─────────────────────────────────────────────────────────

def test_emergency_derisk_triggered():
    rm = _make_risk_manager()
    ps = _make_portfolio(margin_usage="0.90")
    assert rm.check_emergency_derisk(ps) is True


def test_emergency_derisk_not_triggered():
    rm = _make_risk_manager()
    ps = _make_portfolio(margin_usage="0.50")
    assert rm.check_emergency_derisk(ps) is False


def test_emergency_close_coin():
    rm = _make_risk_manager()
    ps = _make_portfolio(positions={
        "BTC": {"size": Decimal("0.1"), "entry_price": Decimal("50000"), "unrealized_pnl": Decimal("-50"), "margin_used": Decimal("100")},
        "ETH": {"size": Decimal("1"), "entry_price": Decimal("3000"), "unrealized_pnl": Decimal("-10"), "margin_used": Decimal("50")},
    })
    worst = rm.get_emergency_close_coin(ps)
    assert worst == "BTC", f"Expected BTC (worst PnL), got {worst}"


# ─── Insufficient balance ────────────────────────────────────────────────────

def test_insufficient_balance():
    rm = _make_risk_manager()
    ps = _make_portfolio(available="10")  # Only $10 available
    order = {"action": "buy", "size": Decimal("0.01"), "leverage": 5, "confidence": 0.9}
    # 0.01 BTC * $50000 / 5x = $100 margin needed, but only $10 available
    ok, reason = rm.check_order("BTC", order, Decimal("50000"), ps, {}, Decimal("0"), time.time())
    assert ok is False
    assert reason == "insufficient_available_balance"


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