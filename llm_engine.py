import json
import logging
import os
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from models import MarketData, PortfolioState, TradingAction
from utils.retry import retry_http

logger = logging.getLogger(__name__)


class LLMEngine:
    """
    LLM Engine using Claude Opus 4 via OpenRouter for trading decisions.
    All market data comes from Hyperliquid; no external data sources.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-opus-4",
        max_tokens: int = 8192,
        temperature: float = 0.2
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/hyperliquid-trading-bot",
            "X-Title": "Hyperliquid Trading Bot"
        })
        logger.info(f"LLM Engine initialized with model={self.model}")

    def _format_positions(self, positions: Dict[str, Dict[str, Any]]) -> str:
        """Format positions for the prompt."""
        if not positions:
            return "  No open positions."
        lines = []
        for coin, pos in positions.items():
            size = pos.get("size", 0)
            entry_px = pos.get("entry_price", 0)
            pnl = pos.get("unrealized_pnl", 0)
            side = "LONG" if Decimal(str(size)) > 0 else "SHORT"
            margin = pos.get("margin_used", "N/A")
            lines.append(
                f"  - {coin}: {side} | Size: {size} | Entry: ${entry_px} | "
                f"Unrealized PnL: ${pnl} | Margin: ${margin}"
            )
        return "\n".join(lines)

    def _format_technical_data(self, technical_data: Optional[Dict[str, Any]]) -> str:
        """Format Hyperliquid technical data for the prompt."""
        if not technical_data:
            return "  No technical data available."
        lines = []
        for key, value in technical_data.items():
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, list):
                        last_values = sub_value[-5:] if len(sub_value) > 5 else sub_value
                        formatted = [f"{float(v):.6f}" if isinstance(v, Decimal) else str(v) for v in last_values]
                        lines.append(f"    {sub_key}: [{', '.join(formatted)}]")
                    else:
                        val_str = f"{float(sub_value):.6f}" if isinstance(sub_value, Decimal) else str(sub_value)
                        lines.append(f"    {sub_key}: {val_str}")
            elif isinstance(value, Decimal):
                lines.append(f"  {key}: {float(value):.6f}")
            else:
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    def _build_prompt(
        self,
        market_data: MarketData,
        portfolio_state: PortfolioState,
        technical_data: Optional[Dict[str, Any]] = None,
        all_mids: Optional[Dict[str, str]] = None,
        funding_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build structured prompt with all Hyperliquid-sourced data."""

        all_mids_section = ""
        if all_mids:
            top_coins = ["BTC", "ETH", "SOL", "BNB", "ADA", "DOGE", "XRP", "AVAX", "MATIC", "DOT"]
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

        prompt = f"""You are an expert cryptocurrency trader operating on Hyperliquid exchange.
ALL data below comes directly from Hyperliquid's API. Make your decision based ONLY on this data.

{all_mids_section}

TARGET ASSET: {market_data.coin}
  Current Price: ${market_data.last_price}
  24h Change: {float(market_data.change_24h) * 100:.4f}%
  24h Volume: ${float(market_data.volume_24h):,.2f}
  Funding Rate: {float(market_data.funding_rate):.6f}%
{funding_section}

TECHNICAL INDICATORS (calculated from Hyperliquid candle data):
{self._format_technical_data(technical_data)}

PORTFOLIO STATE:
  Total Balance: ${portfolio_state.total_balance}
  Available Balance: ${portfolio_state.available_balance}
  Margin Usage: {float(portfolio_state.margin_usage) * 100:.2f}%
  Open Positions Count: {len(portfolio_state.positions)}

CURRENT POSITIONS:
{self._format_positions(portfolio_state.positions)}

TRADING RULES:
- Minimum sizes: BTC 0.001, ETH 0.001, SOL 0.1, BNB 0.001, ADA 16.0
- Maximum leverage: 10x (configurable)
- You MUST respond with ONLY valid JSON, no markdown, no explanation outside JSON
- Use "hold" if uncertain or no clear opportunity
- Confidence must reflect your actual certainty (0.0 to 1.0)
- Consider funding rates for carry trade opportunities
- Factor in current positions before recommending new ones

Respond with this exact JSON structure:
{{
  "action": "buy|sell|hold|close_position|increase_position|reduce_position|change_leverage",
  "size": 0.001,
  "leverage": 5,
  "confidence": 0.75,
  "reasoning": "Detailed analysis explaining the decision based on the data provided"
}}"""
        return prompt.strip()

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response with multiple fallback strategies."""
        # Strategy 1: Direct JSON parse
        cleaned = response_text.strip()
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

        logger.error(f"All JSON parsing strategies failed. Response preview: {cleaned[:300]}...")
        return None

    def _validate_decision(self, parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate and normalize a parsed LLM decision."""
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

    def get_trading_decision(
        self,
        market_data: MarketData,
        portfolio_state: PortfolioState,
        technical_data: Optional[Dict[str, Any]] = None,
        all_mids: Optional[Dict[str, str]] = None,
        funding_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Get trading decision from Claude Opus 4 via OpenRouter."""
        prompt = self._build_prompt(
            market_data, portfolio_state, technical_data, all_mids, funding_data
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an autonomous crypto trading agent on Hyperliquid. "
                        "You analyze market data and respond ONLY with valid JSON trading decisions. "
                        "Never include markdown formatting, code blocks, or explanatory text outside the JSON. "
                        "Think carefully about risk/reward before each decision."
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

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=60
            )

            if response.status_code == 429:
                logger.warning("OpenRouter rate limited. Returning None.")
                return None

            if response.status_code != 200:
                logger.error(
                    f"OpenRouter API error: status={response.status_code}"
                )
                return None

            data = response.json()

            # Check for API-level errors
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

            # Log usage info
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

        except requests.exceptions.Timeout:
            logger.error("LLM API request timed out (60s)")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"LLM API connection error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API request failed: {e}")
            return None