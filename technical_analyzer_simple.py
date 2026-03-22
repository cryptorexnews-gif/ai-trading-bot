"""
Technical Analyzer — Orchestrator for technical analysis.
Combines data fetching, indicator calculation, and trend analysis.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from utils.data_fetcher import HyperliquidDataFetcher as MarketDataFetcher
from utils.technical_indicators import TechnicalIndicators
from utils.trend_analyzer import TrendAnalyzer


class HyperliquidDataFetcher:
    """
    Backward-compatible facade expected by tests/legacy modules.
    Exposes both:
    - market/trend methods (get_technical_indicators, get_candle_snapshot, etc.)
    - direct indicator helpers (calculate_ema, calculate_rsi, calculate_macd, ...)
    """

    def __init__(self):
        self.data_fetcher = MarketDataFetcher()
        self.trend_analyzer = TrendAnalyzer(self.data_fetcher)

    # ─── High-level analysis ──────────────────────────────────────────────

    def get_technical_indicators(self, coin: str) -> Optional[Dict[str, Any]]:
        data = self.trend_analyzer.analyze_multi_timeframe_trend(coin)
        required_keys = ["current_price", "change_24h", "volume_24h", "funding_rate"]
        if not data or not all(k in data for k in required_keys):
            return None
        return data

    def get_volatility_signal(self, coin: str) -> Dict[str, Any]:
        candles = self.data_fetcher.get_candle_snapshot(coin, "5m", 30)
        return TechnicalIndicators.get_volatility_signal(candles, coin)

    def is_trend_confirmed(self, coin: str, volume_threshold: float = 1.5) -> bool:
        return self.trend_analyzer.is_trend_confirmed(coin, Decimal(str(volume_threshold)))

    # ─── Market fetch pass-throughs ───────────────────────────────────────

    def get_all_mids(self, force_refresh: bool = False):
        return self.data_fetcher.get_all_mids(force_refresh=force_refresh)

    def get_meta(self, force_refresh: bool = False):
        return self.data_fetcher.get_meta(force_refresh=force_refresh)

    def get_funding_for_coin(self, coin: str):
        return self.data_fetcher.get_funding_for_coin(coin)

    def get_candle_snapshot(self, coin: str, interval: str = "5m", limit: int = 100):
        return self.data_fetcher.get_candle_snapshot(coin, interval, limit)

    # ─── Indicator compatibility methods (used by tests) ──────────────────

    def calculate_ema(self, prices: List[Decimal], period: int) -> List[Decimal]:
        return TechnicalIndicators.calculate_ema(prices, period)

    def calculate_rsi(self, prices: List[Decimal], period: int = 14) -> List[Decimal]:
        return TechnicalIndicators.calculate_rsi(prices, period)

    def calculate_macd(
        self,
        prices: List[Decimal],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Tuple[List[Decimal], List[Decimal], List[Decimal]]:
        return TechnicalIndicators.calculate_macd(prices, fast_period, slow_period, signal_period)

    def calculate_atr(
        self,
        highs: List[Decimal],
        lows: List[Decimal],
        closes: List[Decimal],
        period: int = 14
    ) -> List[Decimal]:
        return TechnicalIndicators.calculate_atr(highs, lows, closes, period)

    def _calculate_bollinger_bands(
        self,
        prices: List[Decimal],
        period: int = 20,
        std_dev: Decimal = Decimal("2")
    ) -> Dict[str, List[Decimal]]:
        return TechnicalIndicators.calculate_bollinger_bands(prices, period, std_dev)

    def _calculate_vwap(
        self,
        highs: List[Decimal],
        lows: List[Decimal],
        closes: List[Decimal],
        volumes: List[Decimal]
    ) -> Decimal:
        return TechnicalIndicators.calculate_vwap(highs, lows, closes, volumes)


class TechnicalAnalyzer(HyperliquidDataFetcher):
    """Alias moderno mantenuto per il resto del progetto."""
    pass


# Global instance for backward compatibility
technical_fetcher = TechnicalAnalyzer()