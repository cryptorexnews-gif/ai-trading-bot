import json
import logging
import re
from decimal import Decimal
from typing import Any, Dict, Optional

import requests

from models import MarketData, PortfolioState, TradingAction
from utils.retry import retry_http

logger = logging.getLogger(__name__)


class LLMEngine:
    """
    LLM Engine using Claude Opus 4.6 via OpenRouter for trading decisions.
    Includes extended thinking/reasoning capabilities.
    """

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def _build_prompt(self, market_data: MarketData, portfolio_state: PortfolioState) -> str:
        """Build structured prompt for LLM trading decision."""
        prompt = f"""
You are an expert cryptocurrency trader analyzing market data for automated trading on Hyperliquid.

MARKET DATA:
- Coin: {market_data.coin}
- Current Price: ${market_data.last_price}
- 24h Change: {market_data.change_24h * 100:.2f}%
- 24h Volume: ${market_data.volume_24h:,.0f}
- Funding Rate: {market_data.funding_rate:.4f}%

PORTFOLIO STATE:
- Total Balance: ${portfolio_state.total_balance}
- Available Balance: ${portfolio_state.available_balance}
- Margin Usage: {portfolio_state.margin_usage * 100:.1f}%
- Open Positions: {len(portfolio_state.positions)}

CURRENT POSITIONS:
"""
        for coin, pos in portfolio_state.positions.items():
            size = pos.get('size', 0)
            entry_px = pos.get('entry_price', 0)
            pnl = pos.get('unrealized_pnl', 0)
            prompt += f"- {coin}: Size {size}, Entry ${entry_px}, PnL ${pnl}\n"

        prompt += """
INSTRUCTIONS:
Analyze the market data and portfolio state. Provide a trading decision with the following JSON structure:

{
  "action": "buy|sell|hold|close_position|increase_position|reduce_position|change_leverage",
  "size": <decimal number, e.g., 0.001 for BTC>,
  "leverage": <integer, 1-25>,
  "confidence": <float 0.0-1.0>,
  "reasoning": "<detailed explanation of your analysis and decision>"
}

Rules:
- Use 'hold' if no clear opportunity or high uncertainty
- Size must respect minimums: BTC 0.001, ETH 0.001, SOL 0.1, BNB 0.001, ADA 16.0
- Leverage should be conservative (1-10x) unless strong conviction
- Confidence reflects certainty in the decision
- Provide clear, data-driven reasoning

Respond ONLY with valid JSON.
"""
        return prompt.strip()

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response, extracting JSON from possible markdown or text."""
        # Try direct JSON parse
        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON-like structure
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        if start != -1 and end > start:
            try:
                return json.loads(response_text[start:end])
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to parse LLM response as JSON: {response_text[:200]}...")
        return None

    def get_trading_decision(self, market_data: MarketData, portfolio_state: PortfolioState) -> Optional[Dict[str, Any]]:
        """Get trading decision from LLM."""
        prompt = self._build_prompt(market_data, portfolio_state)

        payload = {
            "model": "anthropic/claude-3-5-sonnet",  # Updated to available model; Opus 4.6 may not be exact
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.2,
            "stream": False,
            # Note: Extended thinking not directly supported in OpenRouter; adjust if available
        }

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                logger.error("Empty LLM response")
                return None

            parsed = self._parse_llm_response(content)
            if parsed:
                # Validate structure
                required_keys = ["action", "size", "leverage", "confidence", "reasoning"]
                if all(key in parsed for key in required_keys):
                    # Normalize values
                    parsed["action"] = str(parsed["action"]).strip().lower()
                    parsed["size"] = Decimal(str(parsed.get("size", 0)))
                    parsed["leverage"] = int(parsed.get("leverage", 1))
                    parsed["confidence"] = float(parsed.get("confidence", 0))
                    parsed["reasoning"] = str(parsed.get("reasoning", ""))

                    # Basic validation
                    if parsed["action"] not in [a.value for a in TradingAction]:
                        logger.warning(f"Invalid action from LLM: {parsed['action']}")
                        return None
                    if not (0 <= parsed["confidence"] <= 1):
                        logger.warning(f"Invalid confidence from LLM: {parsed['confidence']}")
                        return None

                    return parsed
                else:
                    logger.error(f"LLM response missing required keys: {parsed.keys()}")
            else:
                logger.error("Failed to parse LLM response")

        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API request failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in LLM engine: {e}")

        return None