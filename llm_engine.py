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
    LLM Engine using Claude Opus 4.6 via OpenRouter for trading decisions.
    All market data comes from Hyperliquid API; no external data sources.

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
        lines.append(f"  24h Change: {float(technical_data.get('change_24h', 0)) * 100:+.2f}%")
        lines.append(f"  Volume 24h: ${float(technical_data.get('volume_24h', 0)):,.0f}")
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
            if rsi_list and len(rsi_list = lt.get("rsi_14", [])
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
- Altcoins (SOL, AVAX, etc.): Max 3x leverage
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
  "reasoning": "Trend analysis: [timeframe alignment] + [entry timing] + [risk assessment]"
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

            if action_match and size_match and leverage_match and confidence_match:
                return {
                    "action": action_match.group(1),
                    "size": float(size_match.group(1)),
                    "leverage": int(leverage_match.group(1)),
                    "confidence": float(confidence_match.group(1)),
                    "reasoning": reasoning_match.group(1) if reasoning_match else "Extracted from partial response"
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
                "confidence": 0.0, "reasoning": f"Original action '{action}' invalid, defaulting to hold."
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
            "confidence": confidence, "reasoning": str(parsed.get("reasoning", ""))
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
            f"leverage={validated['leverage']}, confidence={validated['confidence']:.2f}"
        )
        return validated