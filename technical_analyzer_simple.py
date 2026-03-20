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
        return self.trend_analyzer.analyze_multi_timeframe_trend(coin)

    def get_volatility_signal(self, coin: str) -> dict:
        """Get volatility signal for a coin."""
        candles = self.data_fetcher.get_candle_snapshot(coin, "5m", 30)
        return TechnicalIndicators.get_volatility_signal(candles, coin)

    def is_trend_confirmed(self, coin: str, volume_threshold: float = 1.5) -> bool:
        """Check if trend is confirmed for trading."""
        from decimal import Decimal
        return self.trend_analyzer.is_trend_confirmed(coin, Decimal(str(volume_threshold)))


# Global instance for backward compatibility
technical_fetcher = TechnicalAnalyzer()