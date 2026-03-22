"""
Test unitari per state_store.py — persistenza stato e equity snapshots.
"""

import json
import os
import tempfile
import time
from decimal import Decimal

from state_store import StateStore


def _make_store(tmp_dir: str) -> StateStore:
    state_path = os.path.join(tmp_dir, "state.json")
    metrics_path = os.path.join(tmp_dir, "metrics.json")
    return StateStore(state_path, metrics_path)


# ─── Default state ────────────────────────────────────────────────────────────

def test_load_default_state():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()
        assert state["peak_portfolio_value"] == "0"
        assert state["consecutive_failed_cycles"] == 0
        assert state["trade_history"] == []
        assert state["equity_snapshots"] == []


# ─── Save and load state ─────────────────────────────────────────────────────

def test_save_and_load_state():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()
        state["peak_portfolio_value"] = "1234.56"
        state["consecutive_losses"] = 3
        store.save_state(state)

        loaded = store.load_state()
        assert loaded["peak_portfolio_value"] == "1234.56"
        assert loaded["consecutive_losses"] == 3


# ─── Trade history ────────────────────────────────────────────────────────────

def test_add_trade_record():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()

        trade = {"timestamp": time.time(), "coin": "BTC", "action": "buy", "success": True}
        store.add_trade_record(state, trade)

        assert len(state["trade_history"]) == 1
        assert state["trade_history"][0]["coin"] == "BTC"


def test_trade_history_limit():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()

        for i in range(120):
            store.add_trade_record(state, {"timestamp": i, "coin": f"COIN{i}", "action": "buy"})

        assert len(state["trade_history"]) == 100, "Should keep only last 100 trades"
        assert state["trade_history"][0]["coin"] == "COIN20", "First should be COIN20"


# ─── Equity snapshots ────────────────────────────────────────────────────────

def test_add_equity_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()

        store.add_equity_snapshot(
            state,
            balance=Decimal("1000"),
            unrealized_pnl=Decimal("50"),
            position_count=2,
            margin_usage=Decimal("0.3"),
        )

        assert len(state["equity_snapshots"]) == 1
        snap = state["equity_snapshots"][0]
        assert snap["balance"] == "1000"
        assert snap["total_value"] == "1050"
        assert snap["position_count"] == 2


def test_equity_snapshots_limit():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()

        for i in range(550):
            store.add_equity_snapshot(
                state,
                balance=Decimal(str(1000 + i)),
                unrealized_pnl=Decimal("0"),
                position_count=0,
                margin_usage=Decimal("0"),
            )

        assert len(state["equity_snapshots"]) == 500, "Should keep only last 500 snapshots"


def test_get_equity_snapshots():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()

        for i in range(10):
            store.add_equity_snapshot(
                state, balance=Decimal(str(1000 + i)),
                unrealized_pnl=Decimal("0"), position_count=0, margin_usage=Decimal("0"),
            )

        recent = store.get_equity_snapshots(state, limit=5)
        assert len(recent) == 5
        assert recent[0]["balance"] == "1005"


# ─── Daily notional ──────────────────────────────────────────────────────────

def test_add_daily_notional():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        daily = {}
        daily = store.add_daily_notional(daily, time.time(), Decimal("100"))
        key = store.day_key(time.time())
        assert Decimal(daily[key]) == Decimal("100")

        daily = store.add_daily_notional(daily, time.time(), Decimal("50"))
        assert Decimal(daily[key]) == Decimal("150")


# ─── Performance summary ─────────────────────────────────────────────────────

def test_performance_summary_empty():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()
        summary = store.get_performance_summary(state)
        assert summary["total_trades"] == 0
        assert summary["win_rate"] == 0.0


def test_performance_summary_with_trades():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()

        store.add_trade_record(state, {"action": "buy", "success": True})
        store.add_trade_record(state, {"action": "sell", "success": True})
        store.add_trade_record(state, {"action": "buy", "success": False, "order_status": "not_filled"})
        store.add_trade_record(state, {"action": "buy", "success": False, "order_status": "filled"})
        store.add_trade_record(state, {"action": "hold", "success": True})

        summary = store.get_performance_summary(state)
        assert summary["total_trades"] == 2  # Failed executions excluded from every count
        assert summary["wins"] == 2
        assert summary["losses"] == 0
        assert summary["holds"] == 1
        assert summary["failed_executions"] == 0


# ─── Atomic write safety ─────────────────────────────────────────────────────

def test_atomic_write_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        state = store.load_state()
        store.save_state(state)
        assert os.path.exists(store.state_path)
        # Temp file should not exist
        assert not os.path.exists(store.state_path + ".tmp")


# ─── Migration safety ────────────────────────────────────────────────────────

def test_load_state_with_missing_keys():
    """Old state files missing new keys should get defaults."""
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        # Write a minimal state (simulating old version)
        with open(store.state_path, "w") as f:
            json.dump({"peak_portfolio_value": "500"}, f)

        state = store.load_state()
        assert state["peak_portfolio_value"] == "500"
        assert state["equity_snapshots"] == []  # New key should have default
        assert state["trade_history"] == []


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