import logging
import time
from decimal import Decimal
from typing import Any, Dict

from utils.data_fetcher import HyperliquidDataFetcher
from utils.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """Analyzes trends across multiple timeframes for trend trading strategy."""

    def __init__(self, data_fetcher: HyperliquidDataFetcher):
        self.data_fetcher = data_fetcher
        # Cache trend analysis (15 minutes)
        self._trend_cache: Dict[str, Dict[str, Any]] = {}
        self._trend_cache_at: Dict[str, float] = {}
        self._trend_cache_ttl: float = 900.0  # 15 minuti

    @staticmethod
    def _ema_trend_short_mid(short_ema: Decimal, mid_ema: Decimal) -> str:
        if short_ema > mid_ema:
            return "bullish"
        if short_ema < mid_ema:
            return "bearish"
        return "neutral"

    @staticmethod
    def _ema_trend_9_21_50(ema9: Decimal, ema21: Decimal, ema50: Decimal) -> str:
        if ema9 > ema21 > ema50:
            return "bullish"
        if ema9 < ema21 < ema50:
            return "bearish"
        return "neutral"

    @staticmethod
    def _ema_trend_21_50(ema21: Decimal, ema50: Decimal) -> str:
        if ema21 > ema50:
            return "bullish"
        if ema21 < ema50:
            return "bearish"
        return "neutral"

    def analyze_multi_timeframe_trend(self, coin: str) -> Dict[str, Any]:
        """
        Analyze trend across 1H, 4H, and 1D timeframes.
        Returns trend strength (0-3), direction, and alignment info.
        """
        now = time.time()
        if coin in self._trend_cache and (now - self._trend_cache_at.get(coin, 0)) < self._trend_cache_ttl:
            return self._trend_cache[coin]

        # Get data for each timeframe
        intraday_candles = self.data_fetcher.get_candle_snapshot(coin, "1h", 120)
        hourly_candles = self.data_fetcher.get_candle_snapshot(coin, "4h", 80)
        daily_candles = self.data_fetcher.get_candle_snapshot(coin, "1d", 240)

        if not intraday_candles or len(intraday_candles) < 25:
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

        intraday_trend = self._ema_trend_short_mid(
            ema_9_1h[-1] if ema_9_1h else Decimal("0"),
            ema_21_1h[-1] if ema_21_1h else Decimal("0"),
        )

        # Calculate volume ratio
        current_volume = intraday_volumes[-1] if intraday_volumes else Decimal("0")
        avg_volume = sum(intraday_volumes[-20:]) / Decimal(str(min(20, len(intraday_volumes)))) if intraday_volumes else Decimal("0")
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else Decimal("1")

        # 24h volume (sum of last 24 hourly candles)
        volume_24h = Decimal("0")
        if intraday_volumes:
            volume_24h = sum(intraday_volumes[-24:])

        # Current price: prefer live mid from Hyperliquid allMids, fallback to last 1H close
        current_price = intraday_closes[-1]
        mids = self.data_fetcher.get_all_mids()
        if isinstance(mids, dict) and coin in mids:
            mid_price = Decimal(str(mids.get(coin, "0")))
            if mid_price > 0:
                current_price = mid_price

        # BB position (0-1 scale)
        bb_upper = bollinger_1h["upper"][-1] if bollinger_1h["upper"] else current_price
        bb_lower = bollinger_1h["lower"][-1] if bollinger_1h["lower"] else current_price
        bb_range = bb_upper - bb_lower
        bb_position = ((current_price - bb_lower) / bb_range) if bb_range > 0 else Decimal("0.5")

        # 4H timeframe analysis (primary trend)
        hourly_context = {}
        hourly_trend = "neutral"
        if hourly_candles and len(hourly_candles) >= 50:
            hourly_closes = [c["close"] for c in hourly_candles]
            hourly_highs = [c["high"] for c in hourly_candles]
            hourly_lows = [c["low"] for c in hourly_candles]

            ema_9_4h = TechnicalIndicators.calculate_ema(hourly_closes, 9)
            ema_21_4h = TechnicalIndicators.calculate_ema(hourly_closes, 21)
            ema_50_4h = TechnicalIndicators.calculate_ema(hourly_closes, 50)
            rsi_14_4h = TechnicalIndicators.calculate_rsi(hourly_closes, 14)
            macd_line_4h, signal_line_4h, histogram_4h = TechnicalIndicators.calculate_macd(hourly_closes)
            atr_14_4h = TechnicalIndicators.calculate_atr(hourly_highs, hourly_lows, hourly_closes, 14)
            bollinger_4h = TechnicalIndicators.calculate_bollinger_bands(hourly_closes, 20, Decimal("2"))

            hourly_trend = self._ema_trend_9_21_50(
                ema_9_4h[-1] if ema_9_4h else Decimal("0"),
                ema_21_4h[-1] if ema_21_4h else Decimal("0"),
                ema_50_4h[-1] if ema_50_4h else Decimal("0"),
            )

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
                "trend": hourly_trend,
                "rsi_trend": [rsi_14_4h[i] if i < len(rsi_14_4h) else Decimal("50") for i in range(max(0, len(rsi_14_4h) - 5), len(rsi_14_4h))],
            }

        # 1D timeframe analysis (main trend)
        long_term_context = {}
        daily_trend = "neutral"
        if daily_candles and len(daily_candles) >= 50:
            daily_closes = [c["close"] for c in daily_candles]
            daily_highs = [c["high"] for c in daily_candles]
            daily_lows = [c["low"] for c in daily_candles]

            daily_ema_21 = TechnicalIndicators.calculate_ema(daily_closes, 21)
            daily_ema_50 = TechnicalIndicators.calculate_ema(daily_closes, 50)
            daily_ema_200 = TechnicalIndicators.calculate_ema(daily_closes, 200) if len(daily_closes) >= 200 else [Decimal("0")] * len(daily_closes)
            daily_rsi_14 = TechnicalIndicators.calculate_rsi(daily_closes, 14)
            daily_atr_14 = TechnicalIndicators.calculate_atr(daily_highs, daily_lows, daily_closes, 14)

            daily_trend = self._ema_trend_21_50(
                daily_ema_21[-1] if daily_ema_21 else Decimal("0"),
                daily_ema_50[-1] if daily_ema_50 else Decimal("0"),
            )

            long_term_context = {
                "ema_21": daily_ema_21[-1] if daily_ema_21 else Decimal("0"),
                "ema_50": daily_ema_50[-1] if daily_ema_50 else Decimal("0"),
                "ema_200": daily_ema_200[-1] if daily_ema_200 else Decimal("0"),
                "rsi_14": daily_rsi_14[-1] if daily_rsi_14 else Decimal("50"),
                "atr_14": daily_atr_14[-1] if daily_atr_14 else Decimal("0"),
                "trend": daily_trend,
                "rsi_trend": [daily_rsi_14[i] if i < len(daily_rsi_14) else Decimal("50") for i in range(max(0, len(daily_rsi_14) - 3), len(daily_rsi_14))],
            }

        # Determine overall trend from timeframe votes
        votes = [intraday_trend, hourly_trend, daily_trend]
        bullish_count = sum(1 for v in votes if v == "bullish")
        bearish_count = sum(1 for v in votes if v == "bearish")

        if bullish_count > bearish_count:
            overall_direction = "bullish"
            trend_strength = bullish_count
        elif bearish_count > bullish_count:
            overall_direction = "bearish"
            trend_strength = bearish_count
        else:
            overall_direction = "neutral"
            trend_strength = 0

        trends_aligned = trend_strength >= 2

        # 24h change: use current live price vs previous 1D close when available
        change_24h = Decimal("0")
        if daily_candles and len(daily_candles) >= 2:
            prev_close = daily_candles[-2]["close"]
            if prev_close != 0:
                change_24h = (current_price - prev_close) / prev_close

        funding_data = self.data_fetcher.get_funding_for_coin(coin)

        result = {
            "current_price": current_price,
            "change_24h": change_24h,
            "volume_24h": volume_24h,
            "funding_rate": Decimal(funding_data.get("funding_rate", "0")),
            "trend_direction": overall_direction,
            "trend_strength": int(trend_strength),
            "trends_aligned": trends_aligned,
            "intraday_trend": intraday_trend,
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

        self._trend_cache[coin] = result
        self._trend_cache_at[coin] = now

        return result

    def is_trend_confirmed(self, coin: str, volume_threshold: Decimal = Decimal("1.5")) -> bool:
        """Check if trend is confirmed for 4H/1D strategy."""
        trend_data = self.analyze_multi_timeframe_trend(coin)

        hourly_context = trend_data.get("hourly_context", {})
        long_term = trend_data.get("long_term_context", {})

        ema9_4h = hourly_context.get("ema_9", Decimal("0"))
        ema21_4h = hourly_context.get("ema_21", Decimal("0"))
        ema50_4h = hourly_context.get("ema_50", Decimal("0"))
        primary_direction = self._ema_trend_9_21_50(ema9_4h, ema21_4h, ema50_4h)
        primary_trend_ok = primary_direction in ["bullish", "bearish"]

        daily_trend = long_term.get("trend", "neutral")
        secondary_trend_ok = daily_trend == primary_direction and daily_trend in ["bullish", "bearish"]

        trend_strength = trend_data.get("trend_strength", 0)
        strength_ok = trend_strength >= 2

        volume_ratio = trend_data.get("volume_ratio", Decimal("1"))
        volume_ok = volume_ratio > volume_threshold

        confirmed = primary_trend_ok and secondary_trend_ok and strength_ok and volume_ok
        logger.debug(
            f"{coin} trend confirmed: primary={primary_direction}, secondary={daily_trend}, "
            f"strength={trend_strength}, volume_ratio={volume_ratio}, confirmed={confirmed}"
        )
        return confirmed