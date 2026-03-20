import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from utils.data_fetcher import HyperliquidDataFetcher
from utils.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """Analyzes trends across multiple timeframes for trend trading strategy."""

    def __init__(self, data_fetcher: HyperliquidDataFetcher):
        self.data_fetcher = data_fetcher

    def analyze_multi_timeframe_trend(self, coin: str) -> Dict[str, Any]:
        """
        Analyze trend across 1H, 4H, and 1D timeframes.
        Returns trend strength (0-3), direction, and alignment info.
        """
        # Get data for each timeframe
        intraday_candles = self.data_fetcher.get_candle_snapshot(coin, "1h", 100)
        hourly_candles = self.data_fetcher.get_candle_snapshot(coin, "4h", 50)
        daily_candles = self.data_fetcher.get_candle_snapshot(coin, "1d", 30)

        if not intraday_candles or len(intraday_candles) < 10:
            return {"trend_strength": 0, "trend_direction": "neutral", "trends_aligned": False}

        # Extract price data
        intraday_closes = [c["close"] for c in intraday_candles]
        intraday_highs = [c["high"] for c in intraday_candles]
        intraday_lows = [c["low"] for c in intraday_candles]
        intraday_volumes = [c["volume"] for c in intraday_candles]

        # 1H timeframe analysis (entry timing)
        ema_9_1h = TechnicalIndicators.calculate_ema(intraday_closes, 9)
        ema_21_1h = TechnicalIndicators.calculate_ema(intraday_closes, 21)
        rsi_14_1h = TechnicalIndicators.calculate_rsi(intraday_closes, 14)
        macd_line_1h, signal_line_1h, histogram_1h = TechnicalIndicators.calculate_macd(intraday_closes)
        atr_14_1h = TechnicalIndicators.calculate_atr(intraday_highs, intraday_lows, intraday_closes, 14)
        bollinger_1h = TechnicalIndicators.calculate_bollinger_bands(intraday_closes, 20, Decimal("2"))
        vwap_1h = TechnicalIndicators.calculate_vwap(intraday_highs, intraday_lows, intraday_closes, intraday_volumes)

        # Calculate volume ratio
        current_volume = intraday_volumes[-1] if intraday_volumes else Decimal("0")
        avg_volume = sum(intraday_volumes[-20:]) / Decimal(str(min(20, len(intraday_volumes)))) if intraday_volumes else Decimal("0")
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else Decimal("1")

        # BB position (0-1 scale)
        current_price = intraday_closes[-1]
        bb_upper = bollinger_1h["upper"][-1] if bollinger_1h["upper"] else current_price
        bb_lower = bollinger_1h["lower"][-1] if bollinger_1h["lower"] else current_price
        bb_range = bb_upper - bb_lower
        bb_position = ((current_price - bb_lower) / bb_range) if bb_range > 0 else Decimal("0.5")

        # 4H timeframe analysis (primary trend)
        hourly_context = {}
        if hourly_candles and len(hourly_candles) >= 20:
            hourly_closes = [c["close"] for c in hourly_candles]
            hourly_highs = [c["high"] for c in hourly_candles]
            hourly_lows = [c["low"] for c in hourly_candles]

            ema_9_4h = TechnicalIndicators.calculate_ema(hourly_closes, 9)
            ema_21_4h = TechnicalIndicators.calculate_ema(hourly_closes, 21)
            ema_50_4h = TechnicalIndicators.calculate_ema(hourly_closes, min(50, len(hourly_closes)))
            rsi_14_4h = TechnicalIndicators.calculate_rsi(hourly_closes, 14)
            macd_line_4h, signal_line_4h, histogram_4h = TechnicalIndicators.calculate_macd(hourly_closes)
            atr_14_4h = TechnicalIndicators.calculate_atr(hourly_highs, hourly_lows, hourly_closes, 14)
            bollinger_4h = TechnicalIndicators.calculate_bollinger_bands(hourly_closes, 20, Decimal("2"))

            hourly_context = {
                "ema_9": ema_9_4h[-1] if ema_9_4h else Decimal("0"),
                "ema_21": ema_21_4h[-1] if ema_21_4h else Decimal("0"),
                "ema_50": ema_50_4h[-1] if ema_50_4h else Decimal("0"),
                "rsi_14": rsi_14_4h[-1] if rsi_14_4h else Decimal("50"),
                "macd_line": macd_line_4h[-1] if macd_line_4h else Decimal("0"),
                "macd_signal": signal_line_4h[-1] if signal_line_4h else Decimal("0"),
                "macd_histogram": histogram_4h[-1] if histogram_4h else Decimal("0"),
                "atr_14": atr_14_4h[-1] if atr_14_4h else Decimal("0"),
                "bollinger_upper": bollinger_4h["upper"][-1] if bollinger_4h["upper"] else Decimal("0"),
                "bollinger_middle": bollinger_4h["middle"][-1] if bollinger_4h["middle"] else Decimal("0"),
                "bollinger_lower": bollinger_4h["lower"][-1] if bollinger_4h["lower"] else Decimal("0"),
                "trend": "bullish" if (ema_9_4h and ema_21_4h and ema_9_4h[-1] > ema_21_4h[-1]) else "bearish",
                "rsi_trend": [rsi_14_4h[i] if i < len(rsi_14_4h) else Decimal("50") for i in range(max(0, len(rsi_14_4h)-5), len(rsi_14_4h))],
            }

        # 1D timeframe analysis (main trend)
        long_term_context = {}
        if daily_candles and len(daily_candles) >= 5:
            daily_closes = [c["close"] for c in daily_candles]
            daily_highs = [c["high"] for c in daily_candles]
            daily_lows = [c["low"] for c in daily_candles]

            daily_ema_21 = TechnicalIndicators.calculate_ema(daily_closes, 21)
            daily_ema_50 = TechnicalIndicators.calculate_ema(daily_closes, min(50, len(daily_closes)))
            daily_ema_200 = TechnicalIndicators.calculate_ema(daily_closes, min(200, len(daily_closes)))
            daily_rsi_14 = TechnicalIndicators.calculate_rsi(daily_closes, 14)
            daily_atr_14 = TechnicalIndicators.calculate_atr(daily_highs, daily_lows, daily_closes, 14)

            long_term_context = {
                "ema_21": daily_ema_21[-1] if daily_ema_21 else Decimal("0"),
                "ema_50": daily_ema_50[-1] if daily_ema_50 else Decimal("0"),
                "ema_200": daily_ema_200[-1] if daily_ema_200 else Decimal("0"),
                "rsi_14": daily_rsi_14[-1] if daily_rsi_14 else Decimal("50"),
                "atr_14": daily_atr_14[-1] if daily_atr_14 else Decimal("0"),
                "trend": "bullish" if (daily_ema_21 and daily_ema_50 and daily_ema_21[-1] > daily_ema_50[-1]) else "bearish",
                "rsi_trend": [daily_rsi_14[i] if i < len(daily_rsi_14) else Decimal("50") for i in range(max(0, len(daily_rsi_14)-3), len(daily_rsi_14))],
            }

        # Determine overall trend strength and direction
        trend_strength = 0
        trend_directions = []

        # 1H trend (weaker weight)
        if ema_9_1h and ema_21_1h and ema_9_1h[-1] > ema_21_1h[-1]:
            trend_directions.append("bullish")
            trend_strength += 0.5  # Partial weight for 1H
        elif ema_9_1h and ema_21_1h and ema_9_1h[-1] < ema_21_1h[-1]:
            trend_directions.append("bearish")
            trend_strength += 0.5

        # 4H trend (full weight)
        if hourly_context.get("trend") == "bullish":
            trend_directions.append("bullish")
            trend_strength += 1
        elif hourly_context.get("trend") == "bearish":
            trend_directions.append("bearish")
            trend_strength += 1

        # 1D trend (full weight)
        if long_term_context.get("trend") == "bullish":
            trend_directions.append("bullish")
            trend_strength += 1
        elif long_term_context.get("trend") == "bearish":
            trend_directions.append("bearish")
            trend_strength += 1

        # Determine overall direction
        bullish_count = trend_directions.count("bullish")
        bearish_count = trend_directions.count("bearish")

        if bullish_count > bearish_count:
            overall_direction = "bullish"
        elif bearish_count > bullish_count:
            overall_direction = "bearish"
        else:
            overall_direction = "neutral"

        # Trends are aligned if all directions match the overall direction
        trends_aligned = all(d == overall_direction for d in trend_directions) and len(trend_directions) > 0

        # Current price and change
        current_price = intraday_closes[-1]
        change_24h = Decimal("0")
        if len(daily_closes) >= 2 and daily_closes[-2] != 0:
            change_24h = (daily_closes[-1] - daily_closes[-2]) / daily_closes[-2]

        # Funding rate
        funding_data = self.data_fetcher.get_funding_for_coin(coin)

        return {
            "current_price": current_price,
            "change_24h": change_24h,
            "volume_24h": current_volume,
            "funding_rate": Decimal(funding_data.get("funding_rate", "0")),
            "trend_direction": overall_direction,
            "trend_strength": int(trend_strength),
            "trends_aligned": trends_aligned,
            "volume_ratio": volume_ratio,
            "current_ema9": ema_9_1h[-1] if ema_9_1h else Decimal("0"),
            "current_ema21": ema_21_1h[-1] if ema_21_1h else Decimal("0"),
            "current_rsi_14": rsi_14_1h[-1] if rsi_14_1h else Decimal("50"),
            "current_macd_histogram": histogram_1h[-1] if histogram_1h else Decimal("0"),
            "intraday_atr": atr_14_1h[-1] if atr_14_1h else Decimal("0"),
            "bb_position": bb_position,
            "vwap": vwap_1h,
            "hourly_context": hourly_context,
            "long_term_context": long_term_context,
        }

    def is_trend_confirmed(self, coin: str, volume_threshold: Decimal = Decimal("1.5")) -> bool:
        """Check if trend is confirmed for 4H/1D strategy."""
        trend_data = self.analyze_multi_timeframe_trend(coin)

        # Primary trend (4H): EMA9 > EMA21 > EMA50
        hourly_context = trend_data.get("hourly_context", {})
        ema9_4h = hourly_context.get("ema_9", Decimal("0"))
        ema21_4h = hourly_context.get("ema_21", Decimal("0"))
        ema50_4h = hourly_context.get("ema_50", Decimal("0"))
        primary_trend_ok = ema9_4h > ema21_4h > ema50_4h

        # Secondary trend (1D): Confirm direction
        long_term = trend_data.get("long_term_context", {})
        daily_trend = long_term.get("trend", "neutral")
        secondary_trend_ok = daily_trend in ["bullish", "bearish"]

        # Trend strength: At least 2/3 timeframes aligned
        trend_strength = trend_data.get("trend_strength", 0)
        strength_ok = trend_strength >= 2

        # Volume confirmation
        volume_ratio = trend_data.get("volume_ratio", 1)
        volume_ok = volume_ratio > volume_threshold

        # Minimum duration (simplified check)
        duration_ok = True

        confirmed = primary_trend_ok and secondary_trend_ok and strength_ok and volume_ok and duration_ok
        logger.debug(f"{coin} trend confirmed: primary={primary_trend_ok}, secondary={secondary_trend_ok}, strength={trend_strength}, volume={volume_ok}, duration={duration_ok}")
        return confirmed