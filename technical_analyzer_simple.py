import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

HYPERLIQUID_BASE_URL = "https://api.hyperliquid.xyz"


class HyperliquidDataFetcher:
    """
    Recupera TUTTI i dati di mercato esclusivamente dall'API Hyperliquid.
    Nessuna fonte dati esterna (Binance, CoinGecko, ecc.) è usata.
    Usa Decimal per tutti i calcoli finanziari.
    Include caching per meta/funding per ridurre chiamate API.
    Supporta analisi multi-timeframe (5m, 1h, 4h).
    """

    def __init__(self, base_url: str = HYPERLIQUID_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_at: float = 0.0
        self._meta_cache_ttl: float = 120.0
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at: float = 0.0
        self._mids_cache_ttl: float = 15.0

    def _d(self, value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    def _post_info(self, payload: Dict[str, Any], timeout: int = 15) -> Optional[Any]:
        try:
            response = self.session.post(
                f"{self.base_url}/info",
                json=payload,
                timeout=timeout
            )
            if response.status_code != 200:
                logger.error(f"Hyperliquid /info errore: status={response.status_code}, type={payload.get('type', 'unknown')}")
                return None
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Hyperliquid /info timeout per type={payload.get('type', 'unknown')}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Hyperliquid /info errore connessione: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Hyperliquid /info errore richiesta: {e}")
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

    def get_funding_for_coin(self, coin: str) -> Dict[str, Any]:
        meta = self.get_meta()
        if not meta:
            return {"funding_rate": "0", "open_interest": "0", "premium": "0", "max_leverage": 10}
        for asset in meta.get("universe", []):
            if asset.get("name") == coin:
                return {
                    "funding_rate": str(asset.get("funding", "0")),
                    "open_interest": str(asset.get("openInterest", "0")),
                    "premium": str(asset.get("premium", "0")),
                    "max_leverage": int(asset.get("maxLeverage", 10))
                }
        return {"funding_rate": "0", "open_interest": "0", "premium": "0", "max_leverage": 10}

    def get_candle_snapshot(
        self,
        coin: str,
        interval: str = "5m",
        limit: int = 100
    ) -> Optional[List[Dict[str, Any]]]:
        now_ms = int(time.time() * 1000)
        interval_ms_map = {
            "1m": 60_000, "3m": 180_000, "5m": 300_000,
            "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000
        }
        interval_ms = interval_ms_map.get(interval, 300_000)
        start_ms = now_ms - (interval_ms * limit)

        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_ms,
                "endTime": now_ms
            }
        }

        data = self._post_info(payload, timeout=15)
        if data is None:
            return None
        if not isinstance(data, list):
            logger.error(f"Formato dati candele inaspettato per {coin}: {type(data)}")
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

    def calculate_macd(
        self, prices: List[Decimal], fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Tuple[List[Decimal], List[Decimal], List[Decimal]]:
        ema_fast = self.calculate_ema(prices, fast)
        ema_slow = self.calculate_ema(prices, slow)
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = self.calculate_ema(macd_line, signal)
        histogram = [m - s for m, s in zip(macd_line, signal_line)]
        return macd_line, signal_line, histogram

    def calculate_rsi(self, prices: List[Decimal], period: int = 14) -> List[Decimal]:
        if len(prices) <= period:
            return [Decimal("50")] * len(prices)
        rsi_values: List[Decimal] = [Decimal("50")] * period
        for i in range(period, len(prices)):
            gains: List[Decimal] = []
            losses: List[Decimal] = []
            for j in range(i - period + 1, i + 1):
                change = prices[j] - prices[j - 1] if j > 0 else Decimal("0")
                if change > 0:
                    gains.append(change)
                else:
                    losses.append(abs(change))
            avg_gain = sum(gains) / Decimal(str(period)) if gains else Decimal("0")
            avg_loss = sum(losses) / Decimal(str(period)) if losses else Decimal("0")
            if avg_loss == 0:
                rsi = Decimal("100")
            else:
                rs = avg_gain / avg_loss
                rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
            rsi_values.append(rsi)
        return rsi_values

    def _calculate_atr(
        self, highs: List[Decimal], lows: List[Decimal], closes: List[Decimal], period: int
    ) -> List[Decimal]:
        if len(highs) < period + 1:
            return [Decimal("0")] * len(highs)
        tr_values: List[Decimal] = []
        for i in range(1, len(highs)):
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i - 1])
            tr3 = abs(lows[i] - closes[i - 1])
            tr_values.append(max(tr1, tr2, tr3))
        atr_values = [Decimal("0")] * min(period, len(tr_values))
        for i in range(period, len(tr_values)):
            atr = sum(tr_values[i - period:i]) / Decimal(str(period))
            atr_values.append(atr)
        return atr_values

    def _calculate_bollinger_bands(
        self, prices: List[Decimal], period: int = 20, std_dev_mult: Decimal = Decimal("2")
    ) -> Dict[str, List[Decimal]]:
        if len(prices) < period:
            empty = [Decimal("0")] * len(prices)
            return {"upper": empty, "middle": empty, "lower": empty}
        upper, middle, lower = [], [], []
        for i in range(len(prices)):
            if i < period - 1:
                upper.append(Decimal("0"))
                middle.append(Decimal("0"))
                lower.append(Decimal("0"))
                continue
            window = prices[i - period + 1:i + 1]
            sma = sum(window) / Decimal(str(period))
            variance = sum((p - sma) ** 2 for p in window) / Decimal(str(period))
            std_dev = self._decimal_sqrt(variance)
            middle.append(sma)
            upper.append(sma + (std_dev_mult * std_dev))
            lower.append(sma - (std_dev_mult * std_dev))
        return {"upper": upper, "middle": middle, "lower": lower}

    def _decimal_sqrt(self, value: Decimal) -> Decimal:
        if value <= 0:
            return Decimal("0")
        x = value
        for _ in range(50):
            x = (x + value / x) / Decimal("2")
        return x

    def _calculate_vwap(
        self, highs: List[Decimal], lows: List[Decimal], closes: List[Decimal], volumes: List[Decimal]
    ) -> Decimal:
        if not volumes or not closes:
            return Decimal("0")
        total_volume = sum(volumes)
        if total_volume == 0:
            return closes[-1] if closes else Decimal("0")
        typical_prices = [(h + l + c) / Decimal("3") for h, l, c in zip(highs, lows, closes)]
        vwap = sum(tp * v for tp, v in zip(typical_prices, volumes)) / total_volume
        return vwap

    def get_volatility_signal(self, coin: str) -> Dict[str, Any]:
        """
        Calcola segnale basato su volatilità per timing ciclo adattivo.
        Alta volatilità = cicli più corti, bassa volatilità = cicli più lunghi.
        """
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
        """
        Ottieni indicatori tecnici completi per una coin.
        TUTTI i dati sorgenti da snapshot candele Hyperliquid.
        Multi-timeframe: 5m (intraday), 1h (medium), 4h (long-term).
        """
        # Recupera candele intraday (5m)
        intraday_candles = self.get_candle_snapshot(coin, "5m", 100)
        if not intraday_candles or len(intraday_candles) < 10:
            logger.warning(f"Dati candele intraday insufficienti per {coin}")
            return None

        # Recupera candele medium-term (1h) — NUOVO
        hourly_candles = self.get_candle_snapshot(coin, "1h", 50)

        # Recupera candele longer-term (4h)
        daily_candles = self.get_candle_snapshot(coin, "4h", 50)
        if not daily_candles or len(daily_candles) < 5:
            logger.warning(f"Dati candele 4h insufficienti per {coin}")
            return None

        # Estrai serie prezzi — intraday
        intraday_closes = [c["close"] for c in intraday_candles]
        intraday_highs = [c["high"] for c in intraday_candles]
        intraday_lows = [c["low"] for c in intraday_candles]
        intraday_volumes = [c["volume"] for c in intraday_candles]

        # Estrai serie prezzi — 4h
        daily_closes = [c["close"] for c in daily_candles]
        daily_highs = [c["high"] for c in daily_candles]
        daily_lows = [c["low"] for c in daily_candles]

        # Calcola indicatori intraday
        ema_20 = self.calculate_ema(intraday_closes, 20)
        ema_9 = self.calculate_ema(intraday_closes, 9)
        macd_line, signal_line, histogram = self.calculate_macd(intraday_closes)
        rsi_7 = self.calculate_rsi(intraday_closes, 7)
        rsi_14 = self.calculate_rsi(intraday_closes, 14)
        intraday_atr = self._calculate_atr(intraday_highs, intraday_lows, intraday_closes, 14)
        bollinger = self._calculate_bollinger_bands(intraday_closes, 20)
        vwap = self._calculate_vwap(intraday_highs, intraday_lows, intraday_closes, intraday_volumes)

        # Calcola indicatori 1h — NUOVO
        hourly_context = {}
        if hourly_candles and len(hourly_candles) >= 10:
            hourly_closes = [c["close"] for c in hourly_candles]
            hourly_highs = [c["high"] for c in hourly_candles]
            hourly_lows = [c["low"] for c in hourly_candles]
            hourly_ema_9 = self.calculate_ema(hourly_closes, 9)
            hourly_ema_20 = self.calculate_ema(hourly_closes, 20)
            hourly_rsi_14 = self.calculate_rsi(hourly_closes, 14)
            hourly_macd, hourly_signal, hourly_hist = self.calculate_macd(hourly_closes)
            hourly_atr = self._calculate_atr(hourly_highs, hourly_lows, hourly_closes, 14)

            hourly_context = {
                "ema_9": hourly_ema_9[-1] if hourly_ema_9 else Decimal("0"),
                "ema_20": hourly_ema_20[-1] if hourly_ema_20 else Decimal("0"),
                "rsi_14": hourly_rsi_14[-1] if hourly_rsi_14 else Decimal("50"),
                "macd": hourly_macd[-1] if hourly_macd else Decimal("0"),
                "macd_signal": hourly_signal[-1] if hourly_signal else Decimal("0"),
                "atr_14": hourly_atr[-1] if hourly_atr else Decimal("0"),
                "trend": "bullish" if (hourly_ema_9 and hourly_ema_20 and hourly_ema_9[-1] > hourly_ema_20[-1]) else "bearish",
                "rsi_trend": [hourly_rsi_14[-3] if len(hourly_rsi_14) >= 3 else Decimal("50"),
                              hourly_rsi_14[-2] if len(hourly_rsi_14) >= 2 else Decimal("50"),
                              hourly_rsi_14[-1] if hourly_rsi_14 else Decimal("50")],
            }

        # Calcola indicatori longer-term (4h)
        daily_ema_20 = self.calculate_ema(daily_closes, 20)
        daily_ema_50 = self.calculate_ema(daily_closes, min(50, len(daily_closes)))
        daily_macd, daily_signal, daily_hist = self.calculate_macd(daily_closes)
        daily_rsi_14 = self.calculate_rsi(daily_closes, 14)
        daily_atr_14 = self._calculate_atr(daily_highs, daily_lows, daily_closes, 14)

        # Valori correnti
        current_price = intraday_closes[-1]
        current_volume = intraday_volumes[-1]
        avg_volume = (
            sum(intraday_volumes[-20:]) / Decimal(str(min(20, len(intraday_volumes))))
            if intraday_volumes else Decimal("0")
        )
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else Decimal("1")

        # 24h change
        if len(daily_closes) >= 2 and daily_closes[-2] != 0:
            change_24h = (daily_closes[-1] - daily_closes[-2]) / daily_closes[-2]
        elif len(intraday_closes) >= 2 and intraday_closes[0] != 0:
            change_24h = (intraday_closes[-1] - intraday_closes[0]) / intraday_closes[0]
        else:
            change_24h = Decimal("0")

        volume_24h = sum(intraday_volumes) * current_price if intraday_volumes else Decimal("0")
        funding_data = self.get_funding_for_coin(coin)

        # Posizione banda Bollinger
        bb_upper = bollinger["upper"][-1] if bollinger["upper"] else Decimal("0")
        bb_lower = bollinger["lower"][-1] if bollinger["lower"] else Decimal("0")
        bb_width = bb_upper - bb_lower
        bb_position = ((current_price - bb_lower) / bb_width) if bb_width > 0 else Decimal("0.5")

        # Allineamento trend multi-timeframe
        intraday_trend = "bullish" if (ema_9 and ema_20 and ema_9[-1] > ema_20[-1]) else "bearish"
        daily_trend = "bullish" if (daily_ema_20 and daily_ema_50 and daily_ema_20[-1] > daily_ema_50[-1]) else "bearish"
        hourly_trend = hourly_context.get("trend", "unknown")

        trends_aligned = (intraday_trend == hourly_trend == daily_trend)

        return {
            "current_price": current_price,
            "change_24h": change_24h,
            "volume_24h": volume_24h,
            "funding_rate": self._d(funding_data.get("funding_rate", "0")),
            "open_interest": funding_data.get("open_interest", "0"),
            "vwap": vwap,
            "volume_ratio": volume_ratio,
            "bb_position": bb_position,
            "current_ema9": ema_9[-1] if ema_9 else Decimal("0"),
            "current_ema20": ema_20[-1] if ema_20 else Decimal("0"),
            "current_macd": macd_line[-1] if macd_line else Decimal("0"),
            "current_macd_signal": signal_line[-1] if signal_line else Decimal("0"),
            "current_macd_histogram": histogram[-1] if histogram else Decimal("0"),
            "current_rsi_7": rsi_7[-1] if rsi_7 else Decimal("50"),
            "current_rsi_14": rsi_14[-1] if rsi_14 else Decimal("50"),
            "intraday_atr": intraday_atr[-1] if intraday_atr else Decimal("0"),
            "bollinger_upper": bb_upper,
            "bollinger_middle": bollinger["middle"][-1] if bollinger["middle"] else Decimal("0"),
            "bollinger_lower": bb_lower,
            # Contesto multi-timeframe
            "intraday_trend": intraday_trend,
            "hourly_context": hourly_context,
            "trends_aligned": trends_aligned,
            "long_term_context": {
                "ema_20": daily_ema_20[-1] if daily_ema_20 else Decimal("0"),
                "ema_50": daily_ema_50[-1] if daily_ema_50 else Decimal("0"),
                "macd": daily_macd[-5:],
                "rsi_14": daily_rsi_14[-5:],
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


# Istanza globale
technical_fetcher = HyperliquidDataFetcher()