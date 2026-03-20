import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests

from utils.decimals import safe_decimal, decimal_sqrt
from utils.http import create_robust_session

logger = logging.getLogger(__name__)

HYPERLIQUID_BASE_URL = "https://api.hyperliquid.xyz"


class HyperliquidDataFetcher:
    """
    Fetches ALL market data exclusively from Hyperliquid API.
    No external data sources (Binance, CoinGecko, etc.) are used.
    Uses Decimal for all financial calculations.
    Supports multi-timeframe analysis (1h, 4h, 1d) for trend trading.
    """

    def __init__(self, base_url: str = HYPERLIQUID_BASE_URL):
        self.base_url = base_url
        self.session = create_robust_session()
        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_at: float = 0.0
        self._meta_cache_ttl: float = 120.0
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at: float = 0.0
        self._mids_cache_ttl: float = 15.0
        self._funding_cache: Optional[List[Dict[str, Any]]] = None
        self._funding_cache_at: float = 0.0
        self._funding_cache_ttl: float = 60.0

    def _d(self, value: Any) -> Decimal:
        return safe_decimal(value)

    def _post_info(self, payload: Dict[str, Any], timeout: int = 15) -> Optional[Any]:
        try:
            response = self.session.post(f"{self.base_url}/info", json=payload, timeout=timeout)
            if response.status_code != 200:
                logger.error(f"Hyperliquid /info error: status={response.status_code}, type={payload.get('type', 'unknown')}")
                return None
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Hyperliquid /info timeout for type={payload.get('type', 'unknown')}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Hyperliquid /info connection error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Hyperliquid /info request error: {e}")
            return None

    def get_all_mids(self, force_refresh: bool = False) -> Optional[Dict[str, str]]:
        now = time.time()
        if not force_refresh and self._mids_cache and (now - self._mids_cache_at) < self._mids_cache_ttl:
            return self._mids_cache
        result = self._post_info({"type": "allMids"})
        if result is not None:
            self._mids_cache = result
            self._mids_cache_at = now
        return self._mids_cache

    def get_meta(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        now = time.time()
        if not force_refresh and self._meta_cache and (now - self._meta_cache_at) < self._meta_cache_ttl:
            return self._meta_cache
        result = self._post_info({"type": "meta"})
        if result is not None:
            self._meta_cache = result
            self._meta_cache_at = now
        return self._meta_cache

    def _get_asset_ctxs(self, force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Fetch metaAndAssetCtxs which contains funding rates and open interest."""
        now = time.time()
        if not force_refresh and self._funding_cache and (now - self._funding_cache_at) < self._funding_cache_ttl:
            return self._funding_cache
        result = self._post_info({"type": "metaAndAssetCtxs"})
        if result is not None and isinstance(result, list) and len(result) >= 2:
            self._funding_cache = result
            self._funding_cache_at = now
        return self._funding_cache

    def get_funding_for_coin(self, coin: str) -> Dict[str, Any]:
        """Get funding rate, open interest, and premium from metaAndAssetCtxs."""
        data = self._get_asset_ctxs()
        if not data or len(data) < 2:
            return {"funding_rate": "0", "open_interest": "0", "premium": "0", "max_leverage": 10}

        meta_part = data[0]
        ctx_part = data[1]
        universe = meta_part.get("universe", [])

        for i, asset in enumerate(universe):
            if asset.get("name") == coin:
                max_lev = int(asset.get("maxLeverage", 10))
                if i < len(ctx_part):
                    ctx = ctx_part[i]
                    return {
                        "funding_rate": str(ctx.get("funding", "0")),
                        "open_interest": str(ctx.get("openInterest", "0")),
                        "premium": str(ctx.get("premium", "0")),
                        "max_leverage": max_lev,
                    }
                return {"funding_rate": "0", "open_interest": "0", "premium": "0", "max_leverage": max_lev}

        return {"funding_rate": "0", "open_interest": "0", "premium": "0", "max_leverage": 10}

    def get_candle_snapshot(self, coin: str, interval: str = "5m", limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        now_ms = int(time.time() * 1000)
        interval_ms_map = {
            "1m": 60_000, "3m": 180_000, "5m": 300_000,
            "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000
        }
        interval_ms = interval_ms_map.get(interval, 300_000)
        start_ms = now_ms - (interval_ms * limit)

        data = self._post_info({
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": interval, "startTime": start_ms, "endTime": now_ms}
        }, timeout=15)

        if data is None:
            return None
        if not isinstance(data, list):
            logger.error(f"Unexpected candle data format for {coin}: {type(data)}")
            return None

        candles = []
        for candle in data:
            candles.append({
                "open_time": candle.get("t", 0),
                "open": self._d(candle.get("o", "0")),
                "high": self._d(candle.get("h", "0")),
                "low": self._d(candle.get("l", "0")),
                "close": self._d(candle.get("c", "0")),
                "volume": self._d(candle.get("v", "0")),
            })
        return candles

    def calculate_ema(self, prices: List[Decimal], period: int) -> List[Decimal]:
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

    def calculate_macd(self, prices: List[Decimal], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[Decimal], List[Decimal], List[Decimal]]:
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = self.calculate_ema(macd_line, signal)
        histogram = [m - s for m, s in zip(macd_line, signal_line)]
        return macd_line, signal_line, histogram

    def calculate_rsi(self, prices: List[Decimal], period: int = 14) -> List[Decimal]:
        """Calculate RSI using Wilder's smoothing method (standard)."""
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

    def _calculate_atr(self, highs: List[Decimal], lows: List[Decimal], closes: List[Decimal], period: int) -> List[Decimal]:
        if len(highs) < period + 1:
            return [Decimal("0")] * len(highs)
        tr_values = []
        for i in range(1, len(highs)):
            tr_values.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
        atr_values = [Decimal("0")] * min(period, len(tr_values))
        for i in range(period, len(tr_values)):
            atr_values.append(sum(tr_values[i - period:i]) / Decimal(str(period)))
        return atr_values

    def _calculate_bollinger_bands(self, prices: List[Decimal], period: int = 20, std_dev_mult: Decimal = Decimal("2")) -> Dict[str, List[Decimal]]:
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

    def _calculate_vwap(self, highs: List[Decimal], lows: List[Decimal], closes: List[Decimal], volumes: List[Decimal]) -> Decimal:
        if not volumes or not closes:
            return Decimal("0")
        total_volume = sum(volumes)
        if total_volume == 0:
            return closes[-1] if closes else Decimal("0")
        typical_prices = [(h + l + c) / Decimal("3") for h, l, c in zip(highs, lows, closes)]
        return sum(tp * v for tp, v in zip(typical_prices, volumes)) / total_volume

    def get_volatility_signal(self, coin: str) -> Dict[str, Any]:
        candles = self.get_candle_snapshot(coin, "5m", 30)
        if not candles or len(candles) < 10:
            return {"volatility_level": "normal", "suggested_cycle_sec": 60}

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]

        atr_values = self._calculate_atr(highs, lows, closes, 14)
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

    def get_technical_indicators(self, coin: str) -> Optional[Dict[str, Any]]:
        """Get complete technical indicators for a coin. Multi-timeframe: 1h, 4h, 1d for trend trading."""
        # Timeframes per trend 4h/1d strategy
        intraday_candles = self.get_candle_snapshot(coin, "1h", 100)  # 1h per entry timing
        hourly_candles = self.get_candle_snapshot(coin, "4h", 50)      # 4h per trend primario
        daily_candles = self.get_candle_snapshot(coin, "1d", 30)       # 1d per trend principale
        
        if not intraday_candles or len(intraday_candles) < 10:
            logger.warning(f"Insufficient intraday candle data for {coin}")
            return None

        if not daily_candles or len(daily_candles) < 5:
            logger.warning(f"Insufficient daily candle data for {coin}")
            return None

        # Extract price series — 1h per entry
        intraday_closes = [c["close"] for c in intraday_candles]
        intraday_highs = [c["high"] for c in intraday_candles]
        intraday_lows = [c["low"] for c in intraday_candles]
        intraday_volumes = [c["volume"] for c in intraday_candles]

        # Extract price series — 4h per trend primario
        hourly_closes = [c["close"] for c in hourly_candles] if hourly_candles else []
        hourly_highs = [c["high"] for c in hourly_candles] if hourly_candles else []
        hourly_lows = [c["low"] for c in hourly_candles] if hourly_candles else []

        # Extract price series — 1d per trend principale
        daily_closes = [c["close"] for c in daily_candles]
        daily_highs = [c["high"] for c in daily_candles]
        daily_lows = [c["low"] for c in daily_candles]

        # 1h indicators (entry timing)
        ema_9_1h = self.calculate_ema(intraday_closes, 9)
        ema_21_1h = self.calculate_ema(intraday_closes, 21)
        ema_50_1h = self.calculate_ema(intraday_closes, min(50, len(intraday_closes)))
        rsi_14_1h = self.calculate_rsi(intraday_closes, 14)
        macd_line_1h, signal_line_1h, histogram_1h = self.calculate_macd(intraday_closes)
        atr_14_1h = self._calculate_atr(intraday_highs, intraday_lows, intraday_closes, 14)
        bollinger_1h = self._calculate_bollinger_bands(intraday_closes, 20, Decimal("2"))
        vwap_1h = self._calculate_vwap(intraday_highs, intraday_lows, intraday_closes, intraday_volumes)

        # 4h indicators (primary trend)
        hourly_indicators = {}
        if hourly_candles and len(hourly_candles) >= 20:
            ema_9_4h = self.calculate_ema(hourly_closes, 9)
            ema_21_4h = self.calculate_ema(hourly_closes, 21)
            ema_50_4h = self.calculate_ema(hourly_closes, min(50, len(hourly_closes)))
            rsi_14_4h = self.calculate_rsi(hourly_closes, 14)
            macd_line_4h, signal_line_4h, histogram_4h = self.calculate_macd(hourly_closes)
            atr_14_4h = self._calculate_atr(hourly_highs, hourly_lows, hourly_closes, 14)
            
            hourly_indicators = {
                "ema_9": ema_9_4h[-1] if ema_9_4h else Decimal("0"),
                "ema_21": ema_21_4h[-1] if ema_21_4h else Decimal("0"),
                "ema_50": ema_50_4h[-1] if ema_50_4h else Decimal("0"),
                "rsi_14": rsi_14_4h[-1] if rsi_14_4h else Decimal("50"),
                "macd_line": macd_line_4h[-1] if macd_line_4h else Decimal("0"),
                "macd_signal": signal_line_4h[-1] if signal_line_4h else Decimal("0"),
                "macd_histogram": histogram_4h[-1] if histogram_4h else Decimal("0"),
                "atr_14": atr_14_4h[-1] if atr_14_4h else Decimal("0"),
                "trend": "bullish" if (ema_9_4h and ema_21_4h and ema_9_4h[-1] > ema_21_4h[-1]) else "bearish",
                "rsi_trend": [rsi_14_4h[i] if i < len(rsi_14_4h) else Decimal("50") for i in range(max(0, len(rsi_14_4h)-5), len(rsi_14_4h))],
            }

        # 1d indicators (main trend)
        daily_ema_21 = self.calculate_ema(daily_closes, 21)
        daily_ema_50 = self.calculate_ema(daily_closes, min(50, len(daily_closes)))
        daily_ema_200 = self.calculate_ema(daily_closes, min(200, len(daily_closes)))
        daily_macd, daily_signal, daily_hist = self.calculate_macd(daily_closes)
        daily_rsi_14 = self.calculate_rsi(daily_closes, 14)
        daily_atr_14 = self._calculate_atr(daily_highs, daily_lows, daily_closes, 14)

        # Current values
        current_price = intraday_closes[-1]
        current_volume = intraday_volumes[-1]
        avg_volume = sum(intraday_volumes[-20:]) / Decimal(str(min(20, len(intraday_volumes)))) if intraday_volumes else Decimal("0")
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else Decimal("1")

        # 24h change from daily candles
        if len(daily_closes) >= 2 and daily_closes[-2] != 0:
            change_24h = (daily_closes[-1] - daily_closes[-2]) / daily_closes[-2]
        elif len(intraday_closes) >= 2 and intraday_closes[0] != 0:
            change_24h = (intraday_closes[-1] - intraday_closes[0]) / intraday_closes[0]
        else:
            change_24h = Decimal("0")

        volume_24h = sum(intraday_volumes) * current_price if intraday_volumes else Decimal("0")
        funding_data = self.get_funding_for_coin(coin)

        # Bollinger position (1h)
        bb_upper = bollinger_1h["upper"][-1] if bollinger_1h["upper"] else Decimal("0")
        bb_lower = bollinger_1h["lower"][-1] if bollinger_1h["lower"] else Decimal("0")
        bb_width = bb_upper - bb_lower
        bb_position = ((current_price - bb_lower) / bb_width) if bb_width > 0 else Decimal("0.5")

        # Multi-timeframe trend alignment
        intraday_trend = "bullish" if (ema_9_1h and ema_21_1h and ema_9_1h[-1] > ema_21_1h[-1]) else "bearish"
        hourly_trend = hourly_indicators.get("trend", "unknown")
        daily_trend = "bullish" if (daily_ema_21 and daily_ema_50 and daily_ema_21[-1] > daily_ema_50[-1]) else "bearish"
        
        # Trend strength indicators
        trend_strength = 0
        if intraday_trend == hourly_trend == daily_trend:
            trend_strength = 3  # All timeframes aligned
        elif (intraday_trend == hourly_trend) or (hourly_trend == daily_trend):
            trend_strength = 2  # Two timeframes aligned
        else:
            trend_strength = 1  # No alignment

        # ADX-like trend strength (simplified)
        trend_direction = ""
        if daily_ema_21 and daily_ema_50:
            if daily_ema_21[-1] > daily_ema_50[-1]:
                trend_direction = "uptrend"
            else:
                trend_direction = "downtrend"

        funding_data = self.get_funding_for_coin(coin)

        return {
            "current_price": current_price,
            "change_24h": change_24h,
            "volume_24h": volume_24h,
            "funding_rate": self._d(funding_data.get("funding_rate", "0")),
            "open_interest": funding_data.get("open_interest", "0"),
            "vwap": vwap_1h,
            "volume_ratio": volume_ratio,
            "bb_position": bb_position,
            
            # 1h indicators
            "current_ema9": ema_9_1h[-1] if ema_9_1h else Decimal("0"),
            "current_ema21": ema_21_1h[-1] if ema_21_1h else Decimal("0"),
            "current_ema50": ema_50_1h[-1] if ema_50_1h else Decimal("0"),
            "current_macd": macd_line_1h[-1] if macd_line_1h else Decimal("0"),
            "current_macd_signal": signal_line_1h[-1] if signal_line_1h else Decimal("0"),
            "current_macd_histogram": histogram_1h[-1] if histogram_1h else Decimal("0"),
            "current_rsi_14": rsi_14_1h[-1] if rsi_14_1h else Decimal("50"),
            "intraday_atr": atr_14_1h[-1] if atr_14_1h else Decimal("0"),
            "bollinger_upper": bb_upper,
            "bollinger_middle": bollinger_1h["middle"][-1] if bollinger_1h["middle"] else Decimal("0"),
            "bollinger_lower": bb_lower,
            "bb_position": bb_position,
            "vwap": vwap_1h,
            "volume_ratio": volume_ratio,
            "intraday_trend": intraday_trend,
            "hourly_context": hourly_indicators,
            "trend_strength": trend_strength,
            "trend_direction": trend_direction,
            "trends_aligned": trend_strength == 3,
            "long_term_context": {
                "ema_21": daily_ema_21[-1] if daily_ema_21 else Decimal("0"),
                "ema_50": daily_ema_50[-1] if daily_ema_50 else Decimal("0"),
                "ema_200": daily_ema_200[-1] if daily_ema_200 else Decimal("0"),
                "macd": daily_macd[-5:] if len(daily_macd) >= 5 else [],
                "rsi_14": daily_rsi_14[-5:] if len(daily_rsi_14) >= 5 else [],
                "atr_14": daily_atr_14[-1] if daily_atr_14 else Decimal("0"),
                "current_volume": current_volume,
                "avg_volume": avg_volume,
                "trend": daily_trend,
            }
        }

    def get_open_interest_and_funding(self, coin: str) -> Dict[str, str]:
        funding_data = self.get_funding_for_coin(coin)
        return {
            "open_interest_latest": str(funding_data.get("open_interest", "0")),
            "funding_rate": str(funding_data.get("funding_rate", "0")),
            "premium": str(funding_data.get("premium", "0"))
        }


# Global instance
technical_fetcher = HyperliquidDataFetcher()