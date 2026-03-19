import json
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from models import MarketData, PortfolioState, TradingAction

logger = logging.getLogger(__name__)

# Status codes that are retryable
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class LLMEngine:
    """
    LLM Engine using Claude Opus 4.6 via OpenRouter for trading decisions.
    All market data comes from Hyperliquid; no external data sources.
    Optimized prompt for asymmetric risk/reward profitability.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-opus-4.6",
        max_tokens: int = 8192,
        temperature: float = 0.15
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.request_timeout = 120
        self.max_retries = 2
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/hyperliquid-trading-bot",
            "X-Title": "Hyperliquid Trading Bot"
        })
        logger.info(f"LLM Engine initialized with model={self.model}, timeout={self.request_timeout}s")

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
            # Calculate PnL percentage
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
        key_indicators = [
            "current_price", "change_24h", "volume_24h", "funding_rate",
            "open_interest", "vwap", "volume_ratio", "bb_position",
            "current_ema9", "current_ema20",
            "current_macd", "current_macd_signal", "current_macd_histogram",
            "current_rsi_7", "current_rsi_14",
            "intraday_atr", "bollinger_upper", "bollinger_middle", "bollinger_lower"
        ]
        lines = []
        for key in key_indicators:
            value = technical_data.get(key)
            if value is None:
                continue
            if isinstance(value, Decimal):
                lines.append(f"  {key}: {float(value):.6f}")
            else:
                lines.append(f"  {key}: {value}")

        # Multi-timeframe context
        lines.append(f"  intraday_trend (5m): {technical_data.get('intraday_trend', 'unknown')}")
        lines.append(f"  trends_aligned (5m+1h+4h): {technical_data.get('trends_aligned', False)}")

        # Hourly context
        hourly = technical_data.get("hourly_context", {})
        if hourly:
            lines.append("  hourly_context (1h):")
            for sub_key in ["ema_9", "ema_20", "rsi_14", "macd", "macd_signal", "atr_14", "trend"]:
                sub_value = hourly.get(sub_key)
                if sub_value is not None:
                    val_str = f"{float(sub_value):.6f}" if isinstance(sub_value, Decimal) else str(sub_value)
                    lines.append(f"    {sub_key}: {val_str}")
            rsi_trend = hourly.get("rsi_trend", [])
            if rsi_trend:
                formatted = [f"{float(v):.2f}" if isinstance(v, Decimal) else str(v) for v in rsi_trend]
                lines.append(f"    rsi_trend: [{', '.join(formatted)}]")

        # Long-term context
        lt = technical_data.get("long_term_context", {})
        if lt:
            lines.append(f"  long_term_trend (4h): {lt.get('trend', 'unknown')}")
            for sub_key in ["ema_20", "ema_50", "atr_14", "current_volume", "avg_volume"]:
                sub_value = lt.get(sub_key)
                if sub_value is not None:
                    val_str = f"{float(sub_value):.6f}" if isinstance(sub_value, Decimal) else str(sub_value)
                    lines.append(f"    {sub_key}: {val_str}")
            rsi_list = lt.get("rsi_14", [])
            if rsi_list:
                last_3 = rsi_list[-3:]
                formatted = [f"{float(v):.2f}" if isinstance(v, Decimal) else str(v) for v in last_3]
                lines.append(f"    rsi_14_trend: [{', '.join(formatted)}]")

        return "\n".join(lines)

    def _format_recent_trades(self, recent_trades: List[Dict[str, Any]]) -> str:
        if not recent_trades:
            return "  No recent trades."
        lines = []
        for trade in recent_trades[-5:]:
            success_str = "✓" if trade.get("success") else "✗"
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
            top_coins = ["BTC", "ETH", "SOL", "BNB", "ADA", "DOGE", "XRP", "AVAX"]
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
  Max Allowed Drawdown: 12%
  Consecutive Losing Trades: {consecutive_losses}"""

        total_exposure = portfolio_state.get_total_exposure()
        total_pnl = portfolio_state.get_total_unrealized_pnl()

        recent_trades_section = ""
        if recent_trades:
            recent_trades_section = f"""
RECENT TRADE HISTORY (last 5):
{self._format_recent_trades(recent_trades)}"""

        # Determine trend alignment for emphasis
        trends_aligned = technical_data.get("trends_aligned", False) if technical_data else False
        alignment_note = ""
        if trends_aligned:
            alignment_note = "\n⚡ ALL TIMEFRAMES ALIGNED — higher confidence entries are appropriate."
        else:
            alignment_note = "\n⚠️ TIMEFRAMES DIVERGENT — prefer smaller sizes or hold unless strong edge."

        prompt = f"""You are an elite cryptocurrency trader on Hyperliquid exchange, optimizing for CONSISTENT PROFITABILITY with asymmetric risk/reward.
ALL data below comes directly from Hyperliquid's API. Make your decision based ONLY on this data.

{all_mids_section}

TARGET ASSET: {market_data.coin}
  Current Price: ${market_data.last_price}
  24h Change: {float(market_data.change_24h) * 100:.4f}%
  24h Volume: ${float(market_data.volume_24h):,.2f}
  Funding Rate: {float(market_data.funding_rate):.6f}%
{funding_section}

TECHNICAL INDICATORS (from Hyperliquid candles — multi-timeframe):
{self._format_technical_data(technical_data)}
{alignment_note}

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

=== STRATEGY RULES (FOLLOW STRICTLY) ===

ENTRY CRITERIA — Only open new positions when:
1. Multi-timeframe confluence: At least 2 of 3 timeframes (5m, 1h, 4h) agree on direction
2. RSI confirmation: RSI-14 between 30-45 for longs (oversold bounce), 55-70 for shorts (overbought rejection)
3. Volume confirmation: volume_ratio > 1.2 (above-average volume confirms move)
4. MACD alignment: histogram direction matches trade direction
5. Bollinger position: bb_position < 0.3 for longs (near lower band), > 0.7 for shorts (near upper band)
6. VWAP: Price below VWAP for longs (discount), above VWAP for shorts (premium)

POSITION MANAGEMENT:
- Risk/Reward minimum 1:3 (SL 2%, TP 6%) — the bot handles SL/TP automatically
- If a position is profitable > 3%, consider letting trailing stop manage it (hold)
- If a position is losing > 1.5%, consider closing early if technicals turned against you
- Close positions when the original thesis is invalidated (trend reversal on 1h)
- Reduce position if margin usage > 60%

SIZING RULES:
- Minimum sizes: BTC 0.001, ETH 0.001, SOL 0.1, BNB 0.001, ADA 16.0
- Use leverage 3-7x for high-confidence trades (all timeframes aligned)
- Use leverage 2-4x for medium-confidence trades
- Never exceed 10x leverage
- Max 40% of balance on a single asset

CRITICAL RULES:
- Do NOT open BUY if already SHORT on same asset (close first)
- Do NOT open SELL if already LONG on same asset (close first)
- If drawdown > 8%, ONLY allow close_position or reduce_position or hold
- If consecutive losses > 3, MUST respond with "hold" unless closing a losing position
- If funding rate is extreme (> 0.01% or < -0.01%), factor it into direction bias
- Negative funding = shorts paying longs = bullish pressure
- Positive funding = longs paying shorts = bearish pressure
- If no clear edge exists, ALWAYS hold — preserving capital is paramount

CONFIDENCE SCORING:
- 0.85-1.0: All timeframes aligned + strong volume + clear RSI signal
- 0.72-0.84: 2/3 timeframes aligned + decent volume
- 0.50-0.71: Mixed signals — only for managing existing positions
- Below 0.50: Hold

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "action": "buy|sell|hold|close_position|increase_position|reduce_position|change_leverage",
  "size": 0.001,
  "leverage": 5,
  "confidence": 0.75,
  "reasoning": "Concise analysis: [timeframe alignment] + [key indicator] + [risk/reward assessment]"
}}"""
        return prompt.strip()

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        cleaned = response_text.strip()

        # Strategy 1: Direct JSON parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first complete JSON object with brace matching
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

        # Strategy 4: Regex extraction of individual fields
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

        logger.error(f"All JSON parsing strategies failed. Response preview: {cleaned[:500]}...")
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
                "action": "hold",
                "size": Decimal("0"),
                "leverage": 1,
                "confidence": 0.0,
                "reasoning": f"Original action '{action}' was invalid, defaulting to hold."
            }

        confidence = float(parsed.get("confidence", 0))
        if not (0.0 <= confidence <= 1.0):
            confidence = max(0.0, min(1.0, confidence))
            logger.warning(f"Clamped confidence to {confidence}")

        leverage = int(parsed.get("leverage", 1))
        if leverage < 1:
            leverage = 1
        if leverage > 50:
            leverage = 50

        size = Decimal(str(parsed.get("size", 0)))
        if size < 0:
            size = Decimal("0")

        return {
            "action": action,
            "size": size,
            "leverage": leverage,
            "confidence": confidence,
            "reasoning": str(parsed.get("reasoning", ""))
        }

    def _call_openrouter(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.request_timeout
                )

                if response.status_code == 200:
                    return response.json()

                if response.status_code in RETRYABLE_STATUS_CODES:
                    body_preview = response.text[:200] if response.text else "empty"
                    logger.warning(
                        f"OpenRouter retryable error: status={response.status_code}, "
                        f"attempt={attempt + 1}/{self.max_retries + 1}, body={body_preview}"
                    )
                    if attempt < self.max_retries:
                        wait = (attempt + 1) * 3
                        time.sleep(wait)
                        continue
                    last_error = f"HTTP {response.status_code} after {self.max_retries + 1} attempts"
                else:
                    body_preview = response.text[:300] if response.text else "empty"
                    logger.error(
                        f"OpenRouter non-retryable error: status={response.status_code}, body={body_preview}"
                    )
                    return None

            except requests.exceptions.Timeout:
                logger.warning(
                    f"OpenRouter timeout ({self.request_timeout}s), "
                    f"attempt={attempt + 1}/{self.max_retries + 1}"
                )
                last_error = "timeout"
                if attempt < self.max_retries:
                    time.sleep(2)
                    continue
            except requests.exceptions.ConnectionError as e:
                logger.warning(
                    f"OpenRouter connection error: {e}, "
                    f"attempt={attempt + 1}/{self.max_retries + 1}"
                )
                last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(2)
                    continue
            except requests.exceptions.RequestException as e:
                logger.error(f"OpenRouter request failed (non-retryable): {e}")
                return None

        logger.error(f"OpenRouter all retries exhausted. Last error: {last_error}")
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
            market_data, portfolio_state, technical_data, all_mids, funding_data,
            recent_trades, peak_portfolio_value, consecutive_losses
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an autonomous crypto trading agent on Hyperliquid optimized for CONSISTENT PROFITABILITY. "
                        "You use multi-timeframe confluence (5m, 1h, 4h) to find high-probability entries. "
                        "You target asymmetric risk/reward: cut losers fast (2% SL), let winners run (6% TP + trailing). "
                        "You respond ONLY with valid JSON trading decisions. "
                        "Never include markdown formatting, code blocks, or explanatory text outside the JSON. "
                        "CAPITAL PRESERVATION is your #1 priority — when in doubt, HOLD. "
                        "Only trade when you have genuine edge with multi-timeframe confirmation."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }

        data = self._call_openrouter(payload)
        if data is None:
            return None

        if "error" in data:
            logger.error(f"OpenRouter returned error: {data['error']}")
            return None

        choices = data.get("choices", [])
        if not choices:
            logger.error("OpenRouter returned empty choices")
            return None

        message = choices[0].get("message", {})
        content = message.get("content", "")

        if not content:
            logger.error("Empty content in LLM response")
            return None

        usage = data.get("usage", {})
        if usage:
            logger.info(
                f"LLM usage: prompt_tokens={usage.get('prompt_tokens', 0)}, "
                f"completion_tokens={usage.get('completion_tokens', 0)}, "
                f"total_tokens={usage.get('total_tokens', 0)}"
            )

        parsed = self._parse_llm_response(content)
        if not parsed:
            logger.error("Failed to parse LLM response")
            return None

        validated = self._validate_decision(parsed)
        if validated:
            logger.info(
                f"LLM decision for {market_data.coin}: "
                f"action={validated['action']}, size={validated['size']}, "
                f"leverage={validated['leverage']}, confidence={validated['confidence']}"
            )
        return validated