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
            bollinger_4h = self._calculate_bollinger_bands(hourly_closes, 20, Decimal("2"))  # Bollinger for breakout
            
            hourly_indicators = {
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
        elif len(intraday_closes) >= 2 and intraday_closes[0]<dyad-write path="llm_engine.py" description="Aggiornamento di llm_engine.py per prompt più specifici per trend trading: enfasi su trend persistence, RSI pullback zones, e output strutturato per trend_strength.">
import json
import logging
import re
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from models import MarketData, PortfolioState, TradingAction
from utils.retry import retry_request, RETRYABLE_STATUS_CODES

logger = logging.getLogger(__name__)


class LLMEngine:
    """
    LLM Engine using Claude Opus 4.6 via OpenRouter for trend trading decisions.
    All market data sourced from Hyperliquid API; no external data sources.

    Security: The API key is stored only in the session headers and never logged.
    __repr__ is overridden to prevent accidental leakage.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-opus-4.6",
        max_tokens: int = 8192,
        temperature: float = 0.15
    ):
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.request_timeout = 120
        self.max_retries = 2

        # Plain session without retry adapter — retry_request handles retries
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/hyperliquid-trading-bot",
            "X-Title": "Hyperliquid Trading Bot"
        })
        # Do NOT store api_key as self.api_key — it lives only in session headers
        logger.info(f"LLM Engine initialized with model={self.model}, timeout={self.request_timeout}s")

    def __repr__(self) -> str:
        """Prevent accidental API key leakage in logs/tracebacks."""
        return f"<LLMEngine model={self.model} base_url={self.base_url}>"

    def __str__(self) -> str:
        return self.__repr__()

    def _format_positions(self, positions: Dict[str, Dict[str, Any]]) -> str:
        if not positions:
            return "  No open positions."
        lines = []
        for coin, pos in positions.items():
            size = pos.get("size", 0)
            entry_px = pos.get("entry_price", 0)
            pnl = pos.get("unrealized_pnl", 0)
            side = "LONG" if Decimal(str(size)) > 0 else "SHORT"
            margin = pos.get("margin_used", "N/A")
            entry_d = Decimal(str(entry_px))
            pnl_d = Decimal(str(pnl))
            size_d = abs(Decimal(str(size)))
            pnl_pct = (pnl_d / (size_d * entry_d) * Decimal("100")) if (size_d * entry_d) > 0 else Decimal("0")
            lines.append(
                f"  - {coin}: {side} | Size: {size} | Entry: ${entry_px} | "
                f"PnL: ${pnl} ({float(pnl_pct):+.2f}%) | Margin: ${margin}"
            )
        return "\n".join(lines)

    def _format_technical_data(self, technical_data: Optional[Dict[str, Any]]) -> str:
        if not technical_data:
            return "  No technical data available."
        
        lines = []
        
        # Price and basic info
        lines.append(f"  Current Price: ${float(technical_data.get('current_price', 0)):.2f}")
        lines.append(f"  24h Change: {float(technical_data.get('change_24h', 0)) * 100:+.4f}%")
        lines.append(f"  Volume 24h: ${float(technical_data.get('volume_24h', 0)):,.2f}")
        lines.append(f"  Funding Rate: {float(technical_data.get('funding_rate', 0)) * 100:+.4f}%")
        
        # Trend information
        lines.append(f"  Trend Direction: {technical_data.get('trend_direction', 'neutral').upper()}")
        lines.append(f"  Trend Strength: {technical_data.get('trend_strength', 0)}/3 timeframes aligned")
        lines.append(f"  Trends Aligned: {'YES ✅' if technical_data.get('trends_aligned', False) else 'NO ⚠️'}")
        
        # 1h timeframe (entry timing)
        lines.append("\n  ⏰ 1H TIMEFRAME (Entry Timing):")
        lines.append(f"    EMA9: ${float(technical_data.get('current_ema9', 0)):.2f}")
        lines.append(f"    EMA21: ${float(technical_data.get('current_ema21', 0)):.2f}")
        lines.append(f"    RSI14: {float(technical_data.get('current_rsi_14', 50)):.1f}")
        lines.append(f"    MACD Hist: {float(technical_data.get('current_macd_histogram', 0)):.4f}")
        lines.append(f"    ATR14: ${float(technical_data.get('intraday_atr', 0)):.2f}")
        lines.append(f"    BB Position: {float(technical_data.get('bb_position', 0.5)) * 100:.1f}%")
        lines.append(f"    VWAP: ${float(technical_data.get('vwap', 0)):.2f}")
        lines.append(f"    Volume Ratio: {float(technical_data.get('volume_ratio', 1)):.2f}x")
        
        # 4h timeframe (primary trend)
        hourly = technical_data.get("hourly_context", {})
        if hourly:
            lines.append("\n  📊 4H TIMEFRAME (Primary Trend):")
            lines.append(f"    Trend: {hourly.get('trend', 'unknown').upper()}")
            lines.append(f"    EMA9: ${float(hourly.get('ema_9', 0)):.2f}")
            lines.append(f"    EMA21: ${float(hourly.get('ema_21', 0)):.2f}")
            lines.append(f"    EMA50: ${float(hourly.get('ema_50', 0)):.2f}")
            lines.append(f"    RSI14: {float(hourly.get('rsi_14', 50)):.1f}")
            lines.append(f"    MACD: {float(hourly.get('macd_line', 0)):.4f}")
            lines.append(f"    ATR14: ${float(hourly.get('atr_14', 0)):.2f}")
            lines.append(f"    Bollinger Upper: ${float(hourly.get('bollinger_upper', 0)):.2f}")
            lines.append(f"    Bollinger Lower: ${float(hourly.get('bollinger_lower', 0)):.2f}")
        
        # 1d timeframe (main trend)
        lt = technical_data.get("long_term_context", {})
        if lt:
            lines.append("\n  📈 1D TIMEFRAME (Main Trend):")
            lines.append(f"    Trend: {lt.get('trend', 'unknown').upper()}")
            lines.append(f"    EMA21: ${float(lt.get('ema_21', 0)):.2f}")
            lines.append(f"    EMA50: ${float(lt.get('ema_50', 0)):.2f}")
            lines.append(f"    EMA200: ${float(lt.get('ema_200', 0)):.2f}")
            lines.append(f"    ATR14: ${float(lt.get('atr_14', 0)):.2f}")
            
            rsi_list = lt.get("rsi_14", [])
            if rsi_list and len(rsi_list) >= 3:
                last_3 = rsi_list[-3:]
                lines.append(f"    RSI14 Trend: {', '.join([f'{float(v):.1f}' for v in last_3])}")
        
        return "\n".join(lines)

    def _format_recent_trades(self, recent_trades: List[Dict[str, Any]]) -> str:
        if not recent_trades:
            return "  No recent trades."
        lines = []
        for trade in recent_trades[-5:]:
            success_str = "OK" if trade.get("success") else "FAIL"
            trigger = trade.get("trigger", "ai")
            lines.append(
                f"  - [{success_str}] {trade.get('coin', '?')} {trade.get('action', '?')} "
                f"size={trade.get('size', '?')} @ ${trade.get('price', '?')} "
                f"conf={trade.get('confidence', '?')} trigger={trigger} "
                f"({trade.get('reasoning', '')[:60]})"
            )
        return "\n".join(lines)

    def _build_prompt(
        self,
        market_data: MarketData,
        portfolio_state: PortfolioState,
        technical_data: Optional[Dict[str, Any]] = None,
        all_mids: Optional[Dict[str, str]] = None,
        funding_data: Optional[Dict[str, Any]] = None,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
        peak_portfolio_value: Decimal = Decimal("0"),
        consecutive_losses: int = 0
    ) -> str:

        all_mids_section = ""
        if all_mids:
            top_coins = [
                "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX",
                "LINK", "SUI", "ARB", "OP", "NEAR", "WIF", "PEPE", "INJ",
                "TIA", "SEI", "RENDER", "FET"
            ]
            mid_lines = []
            for coin in top_coins:
                if coin in all_mids:
                    mid_lines.append(f"  {coin}: ${all_mids[coin]}")
            if mid_lines:
                all_mids_section = "MARKET OVERVIEW (Hyperliquid Mid Prices):\n" + "\n".join(mid_lines)

        funding_section = ""
        if funding_data:
            funding_section = f"""
FUNDING DATA (from Hyperliquid):
  Current Funding Rate: {funding_data.get('funding_rate', 'N/A')}
  Open Interest: {funding_data.get('open_interest', 'N/A')}
  Premium: {funding_data.get('premium', 'N/A')}"""

        drawdown_section = ""
        if peak_portfolio_value > 0:
            current_dd = (peak_portfolio_value - portfolio_state.total_balance) / peak_portfolio_value
            drawdown_section = f"""
RISK CONTEXT:
  Peak Portfolio Value: ${peak_portfolio_value}
  Current Drawdown: {float(current_dd) * 100:.2f}%
  Max Allowed Drawdown: 15%
  Consecutive Losing Trades: {consecutive_losses}"""

        total_exposure = portfolio_state.get_total_exposure()
        total_pnl = portfolio_state.get_total_unrealized_pnl()

        recent_trades_section = ""
        if recent_trades:
            recent_trades_section = f"""
RECENT TRADE HISTORY (last 5):
{self._format_recent_trades(recent_trades)}"""

        # Trend analysis
        trend_strength = technical_data.get("trend_strength", 0) if technical_data else 0
        trend_direction = technical_data.get("trend_direction", "neutral") if technical_data else "neutral"
        
        trend_analysis = ""
        if trend_strength == 3:
            trend_analysis = "✅ ALL TIMEFRAMES ALIGNED (1H+4H+1D) — High conviction trend trade opportunity."
        elif trend_strength == 2:
            trend_analysis = "⚠️ TWO TIMEFRAMES ALIGNED — Moderate conviction, wait for better alignment or use smaller size."
        else:
            trend_analysis = "🚫 NO TIMEFRAME ALIGNMENT — Avoid new positions, only manage existing ones."

        prompt = f"""You are an elite cryptocurrency trend trader on Hyperliquid exchange, specialized in 4HOUR and 1DAY trend following.
ALL data below comes directly from the Hyperliquid API. Make your decision based ONLY on this data.

{all_mids_section}

TARGET ASSET: {market_data.coin}
  Current Price: ${market_data.last_price}
  24h Change: {float(market_data.change_24h) * 100:.4f}%
  24h Volume: ${float(market_data.volume_24h):,.2f}
  Funding Rate: {float(market_data.funding_rate):.6f}%
{funding_section}

TECHNICAL INDICATORS (Multi-timeframe analysis for trend trading):
{self._format_technical_data(technical_data)}

{trend_analysis}

PORTFOLIO STATE:
  Total Balance: ${portfolio_state.total_balance}
  Available Balance: ${portfolio_state.available_balance}
  Margin Usage: {float(portfolio_state.margin_usage) * 100:.2f}%
  Total Exposure: ${total_exposure}
  Total Unrealized PnL: ${total_pnl}
  Open Positions: {len(portfolio_state.positions)}
{drawdown_section}

CURRENT POSITIONS:
{self._format_positions(portfolio_state.positions)}
{recent_trades_section}

=== TREND TRADING STRATEGY RULES (4H/1D FOCUS) ===

TREND IDENTIFICATION CRITERIA — Enter ONLY when:
1. PRIMARY TREND (4H): EMA9 > EMA21 > EMA50 (uptrend) or EMA9 < EMA21 < EMA50 (downtrend)
2. MAIN TREND (1D): Confirms primary trend direction
3. TREND STRENGTH: At least 2/3 timeframes aligned (preferably 3/3)
4. VOLUME CONFIRMATION: volume_ratio > 1.3 on breakout/breakdown
5. RSI POSITION: RSI14 between 40-60 for continuation, <30/>70 for reversal setups
6. NO MAJOR DIVERGENCES: Price making higher highs with indicators confirming

ENTRY TIMING (1H timeframe):
- Wait for pullback to key levels: EMA21, VWAP, or previous support/resistance
- RSI14 between 30-40 for longs, 60-70 for shorts (pullback zones)
- MACD histogram turning positive (longs) or negative (shorts)
- Price above VWAP for longs, below VWAP for shorts
- Bollinger Band position <30% for longs, >70% for shorts (reversion to mean)

POSITION MANAGEMENT FOR TREND TRADING:
- Initial Stop Loss: 5% from entry (wider for trend trades)
- Take Profit: 10% minimum (1:2 risk/reward)
- Break-even: Activate at +3% profit, move SL to entry +0.2%
- Trailing Stop: Activate at +5% profit, 3% callback
- Let winners run: If trend remains strong, consider moving TP to 15-20%
- Exit if: 1D trend breaks (EMA21 crosses EMA50), or volume dries up on moves

SIZING & RISK FOR TREND TRADES:
- Maximum 2 open trend positions simultaneously
- Position size: 2-4% of portfolio per trend trade
- Leverage: 3-5x maximum (conservative for overnight holds)
- Never exceed 40% portfolio exposure across all positions
- Blue chips (BTC, ETH): Up to 5x leverage acceptable
- Altcoins (SOL, AVAX, etc.): Max 3x leverage with tight SL
- Meme coins (WIF, PEPE): Avoid or max 2x leverage with tight SL

CRITICAL RULES FOR TREND TRADING:
- DO NOT counter-trend trade (no buying in downtrend, no selling in uptrend)
- If drawdown > 10%, reduce position sizes by 50%
- If consecutive losses > 2, switch to 1% position sizes until recovery
- Monitor funding rates: Extreme positive (>0.01%) = caution on longs
- Monitor funding rates: Extreme negative (<-0.01%) = caution on shorts
- Weekend rule: Reduce leverage by 30% before weekends (higher volatility)
- News events: Avoid opening new positions 1 hour before/after major announcements
- If no clear trend exists, ALWAYS hold — capital preservation is priority #1

CONFIDENCE SCORING FOR TREND TRADES:
- 0.90-1.0: All 3 timeframes aligned + strong volume + clean pullback
- 0.80-0.89: 2/3 timeframes aligned + decent volume + good entry timing
- 0.70-0.79: Trend present but entry timing suboptimal
- 0.60-0.69: Weak trend signal — only for managing existing positions
- Below 0.60: No trade — wait for better setup

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "action": "buy|sell|hold|close_position|increase_position|reduce_position|change_leverage",
  "size": 0.001,
  "leverage": 4,
  "confidence": 0.85,
  "reasoning": "Trend analysis: [timeframe alignment] + [entry timing] + [risk assessment]",
  "trend_strength": "weak|moderate|strong",
  "trend_direction": "uptrend|downtrend|neutral"
}}"""
        return prompt.strip()

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        cleaned = response_text.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        start = cleaned.find('{')
        if start != -1:
            depth = 0
            for i in range(start, len(cleaned)):
                if cleaned[i] == '{':
                    depth += 1
                elif cleaned[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[start:i + 1])
                        except json.JSONDecodeError:
                            break

        try:
            action_match = re.search(r'"action"\s*:\s*"([^"]+)"', cleaned)
            size_match = re.search(r'"size"\s*:\s*([\d.]+)', cleaned)
            leverage_match = re.search(r'"leverage"\s*:\s*(\d+)', cleaned)
            confidence_match = re.search(r'"confidence"\s*:\s*([\d.]+)', cleaned)
            reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned)
            trend_strength_match = re.search(r'"trend_strength"\s*:\s*"([^"]+)"', cleaned)
            trend_direction_match = re.search(r'"trend_direction"\s*:\s*"([^"]+)"', cleaned)

            if action_match and size_match and leverage_match and confidence_match:
                return {
                    "action": action_match.group(1),
                    "size": float(size_match.group(1)),
                    "leverage": int(leverage_match.group(1)),
                    "confidence": float(confidence_match.group(1)),
                    "reasoning": reasoning_match.group(1) if reasoning_match else "Extracted from partial response",
                    "trend_strength": trend_strength_match.group(1) if trend_strength_match else "moderate",
                    "trend_direction": trend_direction_match.group(1) if trend_direction_match else "neutral"
                }
        except (ValueError, AttributeError):
            pass

        logger.error(f"All JSON parse strategies failed. Response preview: {cleaned[:500]}...")
        return None

    def _validate_decision(self, parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        required_keys = ["action", "size", "leverage", "confidence", "reasoning"]
        if not all(key in parsed for key in required_keys):
            missing = [k for k in required_keys if k not in parsed]
            logger.error(f"LLM response missing keys: {missing}")
            return None

        action = str(parsed["action"]).strip().lower()
        valid_actions = {a.value for a in TradingAction}
        if action not in valid_actions:
            logger.warning(f"Invalid action from LLM: '{action}'. Defaulting to hold.")
            return {
                "action": "hold", "size": Decimal("0"), "leverage": 1,
                "confidence": 0.0, "reasoning": f"Original action '{action}' invalid, defaulting to hold.",
                "trend_strength": "weak", "trend_direction": "neutral"
            }

        confidence = float(parsed.get("confidence", 0))
        if not (0.0 <= confidence <= 1.0):
            confidence = max(0.0, min(1.0, confidence))

        leverage = int(parsed.get("leverage", 1))
        leverage = max(1, min(50, leverage))

        size = Decimal(str(parsed.get("size", 0)))
        if size < 0:
            size = Decimal("0")

        return {
            "action": action, "size": size, "leverage": leverage,
            "confidence": confidence, "reasoning": str(parsed.get("reasoning", "")),
            "trend_strength": str(parsed.get("trend_strength", "moderate")),
            "trend_direction": str(parsed.get("trend_direction", "neutral"))
        }

    def _call_openrouter(self, prompt: str) -> Optional[str]:
        """Call OpenRouter API with retry. Error messages never include request headers."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        def _do_request():
            return self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload, timeout=self.request_timeout
            )

        try:
            response = retry_request(
                _do_request, max_attempts=self.max_retries + 1,
                initial_delay=2.0, max_delay=30.0, backoff_factor=2.0, jitter=True,
                retryable_status_codes=RETRYABLE_STATUS_CODES, logger_instance=logger,
            )

            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices", [])
                if choices and choices[0].get("message", {}).get("content"):
                    return choices[0]["message"]["content"]
                logger.error("OpenRouter returned empty choices")
                return None

            logger.error(f"OpenRouter non-retryable error: HTTP {response.status_code}")
            return None

        except requests.exceptions.Timeout:
            logger.error(f"OpenRouter timeout after all retries (timeout={self.request_timeout}s)")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("OpenRouter connection error after all retries")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"OpenRouter HTTP error: status={getattr(e.response, 'status_code', 'unknown')}")
            return None
        except Exception as e:
            logger.error(f"OpenRouter unexpected error: {type(e).__name__}")
            return None

    def get_trading_decision(
        self,
        market_data: MarketData,
        portfolio_state: PortfolioState,
        technical_data: Optional[Dict[str, Any]] = None,
        all_mids: Optional[Dict[str, str]] = None,
        funding_data: Optional[Dict[str, Any]] = None,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
        peak_portfolio_value: Decimal = Decimal("0"),
        consecutive_losses: int = 0
    ) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(
            market_data=market_data, portfolio_state=portfolio_state,
            technical_data=technical_data, all_mids=all_mids,
            funding_data=funding_data, recent_trades=recent_trades,
            peak_portfolio_value=peak_portfolio_value, consecutive_losses=consecutive_losses
        )

        logger.info(f"Requesting LLM decision for {market_data.coin} (prompt ~{len(prompt)} chars)")

        response_text = self._call_openrouter(prompt)
        if not response_text:
            logger.error(f"No response from LLM for {market_data.coin}")
            return None

        logger.debug(f"LLM raw response for {market_data.coin}: {response_text[:300]}...")

        parsed = self._parse_llm_response(response_text)
        if not parsed:
            logger.error(f"Failed to parse LLM response for {market_data.coin}")
            return None

        validated = self._validate_decision(parsed)
        if not validated:
            logger.error(f"Failed to validate LLM decision for {market_data.coin}")
            return None

        logger.info(
            f"LLM decision for {market_data.coin}: "
            f"action={validated['action']}, size={validated['size']}, "
            f"leverage={validated['leverage']}, confidence={validated['confidence']:.2f}, "
            f"trend_strength={validated['trend_strength']}, trend_direction={validated['trend_direction']}"
        )
        return validated