"""
Technical Analyzer — Orchestrator for technical analysis.
Combines data fetching, indicator calculation, and trend analysis.
"""

from utils.data_fetcher import HyperliquidDataFetcher
from utils.technical_indicators import TechnicalIndicators
from utils.trend_analyzer import TrendAnalyzer


class TechnicalAnalyzer:
    """Main orchestrator for technical analysis combining all modules."""

    def __init__(self):
        self.data_fetcher = HyperliquidDataFetcher()
        self.indicators = TechnicalIndicators()
        self.trend_analyzer = TrendAnalyzer(self.data_fetcher)

    def get_technical_indicators(self, coin: str) -> dict:
        """Get complete technical indicators for a coin."""
        data = self.trend_analyzer.analyze_multi_timeframe_trend(coin)

        # Defensive validation: skip coin safely if payload is incomplete.
        required_keys = ["current_price", "change_24h", "volume_24h", "funding_rate"]
        if not data or not all(k in data for k in required_keys):
            return None

        return data

    def get_volatility_signal(self, coin: str) -> dict:
        """Get volatility signal for a coin."""
        candles = self.data_fetcher.get_candle_snapshot(coin, "5m", 30)
        return TechnicalIndicators.get_volatility_signal(candles, coin)

    def is_trend_confirmed(self, coin: str, volume_threshold: float = 1.5) -> bool:
        """Check if trend is confirmed for trading."""
        from decimal import Decimal
        return self.trend_analyzer.is_trend_confirmed(coin, Decimal(str(volume_threshold)))

    # Compatibility pass-throughs expected by orchestrator/engines
    def get_all_mids(self, force_refresh: bool = False):
        return self.data_fetcher.get_all_mids(force_refresh=force_refresh)

    def get_meta(self, force_refresh: bool = False):
        return self.data_fetcher.get_meta(force_refresh=force_refresh)

    def get_funding_for_coin(self, coin: str):
        return self.data_fetcher.get_funding_for_coin(coin)

    def get_candle_snapshot(self, coin: str, interval: str = "5m", limit: int = 100):
        return self.data_fetcher.get_candle_snapshot(coin, interval, limit)


# Global instance for backward compatibility
technical_fetcher = TechnicalAnalyzer()