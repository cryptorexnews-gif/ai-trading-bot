import logging
from decimal import Decimal
from typing import Dict, List, Tuple

from utils.decimals import decimal_sqrt

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Collection of technical indicator calculation functions."""

    @staticmethod
    def calculate_ema(prices: List[Decimal], period: int) -> List[Decimal]:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return [Decimal("0")] * len(prices)
        ema_values: List[Decimal] = []
        multiplier = Decimal("2") / Decimal(str(period + 1))
        sma = sum(prices[:period]) / Decimal(str(period))
        ema_values.extend([sma] * (period - 1))
        ema_values.append(sma)
        for i in range(period, len(prices)):
            ema = (prices[i] * multiplier) + (ema_values[i - 1] * (Decimal("1") - multiplier))
            ema_values.append(ema)
        return ema_values

    @staticmethod
    def calculate_macd(prices: List[Decimal], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[Decimal], List[Decimal], List[Decimal]]:
        """Calculate MACD (Moving Average Convergence Divergence)."""
        ema_fast = TechnicalIndicators.calculate_ema(prices, fast)
        ema_slow = TechnicalIndicators.calculate_ema(prices, slow)
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = TechnicalIndicators.calculate_ema(macd_line, signal)
        histogram = [m - s for m, s in zip(macd_line, signal_line)]
        return macd_line, signal_line, histogram

    @staticmethod
    def calculate_rsi(prices: List[Decimal], period: int = 14) -> List[Decimal]:
        """Calculate RSI using Wilder's smoothing method."""
        if len(prices) <= period:
            return [Decimal("50")] * len(prices)

        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [max(c, Decimal("0")) for c in changes]
        losses = [abs(min(c, Decimal("0"))) for c in changes]

        avg_gain = sum(gains[:period]) / Decimal(str(period))
        avg_loss = sum(losses[:period]) / Decimal(str(period))

        rsi_values: List[Decimal] = [Decimal("50")] * period

        if avg_loss == 0:
            rsi_values.append(Decimal("100"))
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(Decimal("100") - (Decimal("100") / (Decimal("1") + rs)))

        period_d = Decimal(str(period))
        period_minus_1 = Decimal(str(period - 1))

        for i in range(period, len(changes)):
            avg_gain = (avg_gain * period_minus_1 + gains[i]) / period_d
            avg_loss = (avg_loss * period_minus_1 + losses[i]) / period_d
            if avg_loss == 0:
                rsi_values.append(Decimal("100"))
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(Decimal("100") - (Decimal("100") / (Decimal("1") + rs)))

        return rsi_values

    @staticmethod
    def calculate_atr(highs: List[Decimal], lows: List[Decimal], closes: List[Decimal], period: int) -> List[Decimal]:
        """Calculate Average True Range."""
        if len(highs) < period + 1:
            return [Decimal("0")] * len(highs)
        tr_values = []
        for i in range(1, len(highs)):
            tr_values.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
        atr_values = [Decimal("0")] * min(period, len(tr_values))
        for i in range(period, len(tr_values)):
            atr_values.append(sum(tr_values[i - period:i]) / Decimal(str(period)))
        return atr_values

    @staticmethod
    def calculate_bollinger_bands(prices: List[Decimal], period: int = 20, std_dev_mult: Decimal = Decimal("2")) -> Dict[str, List[Decimal]]:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            empty = [Decimal("0")] * len(prices)
            return {"upper": empty, "middle": empty, "lower": empty}
        upper, middle, lower = [], [], []
        for i in range(len(prices)):
            if i < period - 1:
                upper.append(Decimal("0")); middle.append(Decimal("0")); lower.append(Decimal("0"))
                continue
            window = prices[i - period + 1:i + 1]
            sma = sum(window) / Decimal(str(period))
            variance = sum((p - sma) ** 2 for p in window) / Decimal(str(period))
            std_dev = decimal_sqrt(variance)
            middle.append(sma)
            upper.append(sma + (std_dev_mult * std_dev))
            lower.append(sma - (std_dev_mult * std_dev))
        return {"upper": upper, "middle": middle, "lower": lower}

    @staticmethod
    def calculate_vwap(highs: List[Decimal], lows: List[Decimal], closes: List[Decimal], volumes: List[Decimal]) -> Decimal:
        """Calculate Volume Weighted Average Price."""
        if not volumes or not closes:
            return Decimal("0")
        total_volume = sum(volumes)
        if total_volume == 0:
            return closes[-1] if closes else Decimal("0")
        typical_prices = [(h + l + c) / Decimal("3") for h, l, c in zip(highs, lows, closes)]
        return sum(tp * v for tp, v in zip(typical_prices, volumes)) / total_volume

    @staticmethod
    def get_volatility_signal(candles: List[Dict[str, Any]], coin: str) -> Dict[str, Any]:
        """Calculate volatility signal from candle data."""
        if not candles or len(candles) < 10:
            return {"volatility_level": "normal", "suggested_cycle_sec": 60}

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]

        atr_values = TechnicalIndicators.calculate_atr(highs, lows, closes, 14)
        current_atr = atr_values[-1] if atr_values else Decimal("0")
        current_price = closes[-1] if closes else Decimal("1")

        if current_price == 0:
            return {"volatility_level": "normal", "suggested_cycle_sec": 60}

        atr_pct = (current_atr / current_price) * Decimal("100")

        if atr_pct > Decimal("1.5"):
            return {"volatility_level": "extreme", "suggested_cycle_sec": 20, "atr_pct": float(atr_pct)}
        elif atr_pct > Decimal("0.8"):
            return {"volatility_level": "high", "suggested_cycle_sec": 30, "atr_pct": float(atr_pct)}
        elif atr_pct > Decimal("0.3"):
            return {"volatility_level": "normal", "suggested_cycle_sec": 60, "atr_pct": float(atr_pct)}
        else:
            return {"volatility_level": "low", "suggested_cycle_sec": 120, "atr_pct": float(atr_pct)}