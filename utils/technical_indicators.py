import logging
from decimal import Decimal
from typing import Dict, List, Tuple, Any

from utils.decimals import decimal_sqrt

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Static methods for calculating technical indicators."""

    @staticmethod
    def calculate_ema(prices: List[Decimal], period: int) -> List[Decimal]:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return [Decimal("0")] * len(prices)

        ema = [Decimal("0")] * len(prices)
        multiplier = Decimal("2") / (period + 1)

        # First EMA is SMA
        ema[period - 1] = sum(prices[:period]) / period

        # Calculate subsequent EMAs
        for i in range(period, len(prices)):
            ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]

        return ema

    @staticmethod
    def calculate_rsi(prices: List[Decimal], period: int = 14) -> List[Decimal]:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return [Decimal("50")] * len(prices)

        rsi = [Decimal("50")] * len(prices)
        gains = []
        losses = []

        # Calculate price changes
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            gains.append(max(change, Decimal("0")))
            losses.append(max(-change, Decimal("0")))

        # Calculate initial averages
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        if avg_loss == 0:
            rsi[period] = Decimal("100")
        else:
            rs = avg_gain / avg_loss
            rsi[period] = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

        # Calculate subsequent RSIs
        for i in range(period + 1, len(prices)):
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period

            if avg_loss == 0:
                rsi[i] = Decimal("100")
            else:
                rs = avg_gain / avg_loss
                rsi[i] = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

        return rsi

    @staticmethod
    def calculate_macd(prices: List[Decimal], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[List[Decimal], List[Decimal], List[Decimal]]:
        """Calculate MACD (Moving Average Convergence Divergence)."""
        if len(prices) < slow_period:
            length = len(prices)
            return [Decimal("0")] * length, [Decimal("0")] * length, [Decimal("0")] * length

        fast_ema = TechnicalIndicators.calculate_ema(prices, fast_period)
        slow_ema = TechnicalIndicators.calculate_ema(prices, slow_period)

        macd_line = []
        for i in range(len(prices)):
            if fast_ema[i] == 0 or slow_ema[i] == 0:
                macd_line.append(Decimal("0"))
            else:
                macd_line.append(fast_ema[i] - slow_ema[i])

        signal_line = TechnicalIndicators.calculate_ema(macd_line, signal_period)

        histogram = []
        for i in range(len(macd_line)):
            if macd_line[i] == 0 or signal_line[i] == 0:
                histogram.append(Decimal("0"))
            else:
                histogram.append(macd_line[i] - signal_line[i])

        return macd_line, signal_line, histogram

    @staticmethod
    def calculate_atr(highs: List[Decimal], lows: List[Decimal], closes: List[Decimal], period: int = 14) -> List[Decimal]:
        """Calculate Average True Range."""
        if len(highs) < period + 1:
            return [Decimal("0")] * len(highs)

        tr_values = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            tr_values.append(tr)

        if len(tr_values) < period:
            return [Decimal("0")] * len(highs)

        atr = [Decimal("0")] * len(highs)
        atr[period] = sum(tr_values[:period]) / period

        for i in range(period + 1, len(highs)):
            atr[i] = (atr[i - 1] * (period - 1) + tr_values[i - 1]) / period

        return atr

    @staticmethod
    def calculate_bollinger_bands(prices: List[Decimal], period: int = 20, std_dev: Decimal = Decimal("2")) -> Dict[str, List[Decimal]]:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            length = len(prices)
            return {
                "upper": [Decimal("0")] * length,
                "middle": [Decimal("0")] * length,
                "lower": [Decimal("0")] * length
            }

        upper = [Decimal("0")] * len(prices)
        middle = [Decimal("0")] * len(prices)
        lower = [Decimal("0")] * len(prices)

        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1:i + 1]
            avg = sum(window) / period
            variance = sum((x - avg) ** 2 for x in window) / period
            std = decimal_sqrt(variance)

            middle[i] = avg
            upper[i] = avg + std_dev * std
            lower[i] = avg - std_dev * std

        return {"upper": upper, "middle": middle, "lower": lower}

    @staticmethod
    def calculate_vwap(highs: List[Decimal], lows: List[Decimal], closes: List[Decimal], volumes: List[Decimal]) -> Decimal:
        """Calculate Volume Weighted Average Price."""
        if len(highs) != len(lows) or len(lows) != len(closes) or len(closes) != len(volumes):
            return Decimal("0")

        if len(volumes) == 0 or all(v == 0 for v in volumes):
            return closes[-1] if closes else Decimal("0")

        total_volume = sum(volumes)
        if total_volume == 0:
            return closes[-1] if closes else Decimal("0")

        typical_prices = []
        for i in range(len(highs)):
            typical_price = (highs[i] + lows[i] + closes[i]) / Decimal("3")
            typical_prices.append(typical_price * volumes[i])

        return sum(typical_prices) / total_volume

    @staticmethod
    def get_volatility_signal(candles: List[Dict[str, Any]], coin: str) -> Dict[str, Any]:
        """Analyze volatility and suggest cycle timing."""
        if len(candles) < 20:
            return {"volatility_level": "unknown", "suggested_cycle_sec": 1800, "atr_pct": 0.0}

        closes = [Decimal(str(c.get("close", 0))) for c in candles]
        highs = [Decimal(str(c.get("high", 0))) for c in candles]
        lows = [Decimal(str(c.get("low", 0))) for c in candles]

        atr = TechnicalIndicators.calculate_atr(highs, lows, closes, 14)
        current_atr = atr[-1] if atr else Decimal("0")
        current_price = closes[-1] if closes else Decimal("0")

        if current_price == 0:
            return {"volatility_level": "unknown", "suggested_cycle_sec": 1800, "atr_pct": 0.0}

        atr_pct = (current_atr / current_price) * Decimal("100")

        if atr_pct > Decimal("2"):
            return {"volatility_level": "high", "suggested_cycle_sec": 900, "atr_pct": float(atr_pct)}  # 15 minuti
        elif atr_pct > Decimal("1"):
            return {"volatility_level": "medium", "suggested_cycle_sec": 1800, "atr_pct": float(atr_pct)}  # 30 minuti
        else:
            return {"volatility_level": "low", "suggested_cycle_sec": 3600, "atr_pct": float(atr_pct)}  # 60 minuti