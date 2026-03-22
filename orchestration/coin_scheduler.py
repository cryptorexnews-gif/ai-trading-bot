import logging
from decimal import Decimal
from typing import Dict, List, Tuple

from bot_live_writer import write_live_status
from technical_analyzer_simple import technical_fetcher

logger = logging.getLogger(__name__)


class CoinScheduler:
    """Schedules and runs per-coin analysis/execution flow with open-position priority."""

    def __init__(self, correlation_engine, coin_processor):
        self.correlation_engine = correlation_engine
        self.coin_processor = coin_processor

    def analyze_and_trade(
        self,
        trading_pairs: List[str],
        cycle_count: int,
        execution_mode: str,
        portfolio,
        state: Dict,
        daily_notional_used: Decimal,
        peak: Decimal,
        consecutive_losses: int,
        shutdown_requested: bool,
    ) -> Tuple[int, Decimal]:
        correlations = self.correlation_engine.calculate_correlations(trading_pairs, "1h", 50)
        corr_summary = self.correlation_engine.get_correlation_summary(correlations)
        if corr_summary["high_correlation_pairs"]:
            logger.info(f"High correlation pairs: {corr_summary['high_correlation_pairs'][:5]}")

        all_mids = technical_fetcher.get_all_mids()
        recent_trades = self.coin_processor.state_store.get_recent_trades(state, count=5)

        trades_executed = 0
        notional_added = Decimal("0")
        current_portfolio = portfolio

        open_position_coins = [
            coin for coin, pos in current_portfolio.positions.items()
            if Decimal(str(pos.get("size", 0))) != 0
        ]

        analysis_coins: List[str] = []
        for coin in open_position_coins + trading_pairs:
            if coin not in analysis_coins:
                analysis_coins.append(coin)

        logger.info(
            f"Cycle analysis set: {len(analysis_coins)} coins "
            f"(open_positions_first={open_position_coins})"
        )

        for coin in analysis_coins:
            if shutdown_requested:
                logger.info("Shutdown requested, stopping coin analysis")
                break

            has_open_position = coin in current_portfolio.positions and Decimal(str(current_portfolio.positions[coin].get("size", 0))) != 0
            if trades_executed >= self.coin_processor.cfg.max_trades_per_cycle and not has_open_position:
                continue

            logger.info(f"--- Analyzing {coin} ---")
            write_live_status(
                is_running=True,
                execution_mode=execution_mode,
                cycle_count=cycle_count,
                last_cycle_duration=0,
                portfolio=current_portfolio,
                current_coin=coin,
            )

            result = self.coin_processor.process_single_coin(
                coin=coin,
                portfolio=current_portfolio,
                state=state,
                daily_notional_used=daily_notional_used + notional_added,
                peak=peak,
                consecutive_losses=consecutive_losses,
                all_mids=all_mids,
                recent_trades=recent_trades,
                correlations=correlations,
            )

            if result is not None:
                trades_executed += result["trades"]
                notional_added += result["notional"]

                if result["trades"] > 0:
                    state["consecutive_losses"] = 0
                    current_portfolio = self.coin_processor.portfolio_service.get_portfolio_state()
                    self.coin_processor.position_manager.sync_with_exchange(current_portfolio.positions)
                elif result.get("failed"):
                    state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1

        return trades_executed, notional_added