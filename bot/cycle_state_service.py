import time
from decimal import Decimal
from typing import Any, Dict


class CycleStateService:
    """Handles cycle state loading, daily values extraction, and persistence updates."""

    def load_cycle_state(self, state_store) -> Dict[str, Any]:
        state = state_store.load_state()
        daily_key = state_store.day_key(time.time())
        daily_notional_used = Decimal(str(state.get("daily_notional_by_day", {}).get(daily_key, "0")))
        peak = Decimal(str(state.get("peak_portfolio_value", "0")))
        consecutive_losses = int(state.get("consecutive_losses", 0))
        return {
            "state": state,
            "daily_notional_used": daily_notional_used,
            "peak": peak,
            "consecutive_losses": consecutive_losses,
        }

    def add_equity_snapshot(self, state_store, state: Dict[str, Any], portfolio) -> None:
        state_store.add_equity_snapshot(
            state,
            balance=portfolio.total_balance,
            unrealized_pnl=portfolio.get_total_unrealized_pnl(),
            position_count=len(portfolio.positions),
            margin_usage=portfolio.margin_usage,
        )

    def persist_cycle_success(
        self,
        state_store,
        metrics,
        state: Dict[str, Any],
        portfolio,
        peak: Decimal,
        notional_added: Decimal,
    ) -> None:
        if notional_added > 0:
            state["daily_notional_by_day"] = state_store.add_daily_notional(
                state.get("daily_notional_by_day", {}),
                time.time(),
                notional_added
            )

        if portfolio.total_balance > peak:
            state["peak_portfolio_value"] = str(portfolio.total_balance)
            metrics.set_gauge("peak_portfolio_value", portfolio.total_balance)

        state["consecutive_failed_cycles"] = 0
        state_store.save_state(state)

    def persist_cycle_failure(self, state_store) -> None:
        state = state_store.load_state()
        state["consecutive_failed_cycles"] = state.get("consecutive_failed_cycles", 0) + 1
        state_store.save_state(state)