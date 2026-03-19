import json
import logging
from decimal import Decimal
from typing import Any, Dict, List

import requests

from models import PortfolioState, TradingAction

logger = logging.getLogger(__name__)


class LLMEngine:
    def __init__(
        self,
        session: requests.Session,
        api_key: str,
        allow_external_llm: bool,
        include_portfolio_context: bool,
        fallback_mode: str,
        trading_pairs: List[str],
        min_size_by_coin: Dict[str, Decimal],
        hard_max_leverage: Decimal
    ):
        self.session = session
        self.api_key = api_key
        self.allow_external_llm = allow_external_llm
        self.include_portfolio_context = include_portfolio_context
        self.fallback_mode = fallback_mode
        self.trading_pairs = trading_pairs
        self.min_size_by_coin = min_size_by_coin
        self.hard_max_leverage = hard_max_leverage
        self.allowed_actions = {action.value for action in TradingAction}

    def _safe_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        return Decimal(str(value)) if value is not None else default

    def _build_prompt(self, market_data: Dict[str, Any], portfolio_state: PortfolioState) -> str:
        lines = [
            "You are an expert cryptocurrency trading analyst.",
            "Return ONLY valid JSON array with one object per coin.",
            "",
            "MARKET DATA:"
        ]

        for coin, data in market_data.items():
            lines.append(
                f"- {coin}: price={data.last_price}, change_24h={data.change_24h}, volume_24h={data.volume_24h}"
            )

        if self.include_portfolio_context:
            margin_pct = (portfolio_state.margin_usage * Decimal("100")).quantize(Decimal("0.1"))
            lines.extend([
                "",
                "PORTFOLIO CONTEXT:",
                f"- Balance: {portfolio_state.total_balance}",
                f"- Available: {portfolio_state.available_balance}",
                f"- Margin usage: {margin_pct}%",
                f"- Open positions: {len(portfolio_state.positions)}"
            ])

        lines.extend([
            "",
            "ACTION values must be one of:",
            "buy, sell, hold, close_position, increase_position, reduce_position, change_leverage",
            "",
            "Return format example:",
            "[",
            "{\"coin\":\"BTC\",\"action\":\"hold\",\"size\":0,\"leverage\":1,\"confidence\":0.5,\"reasoning\":\"...\"}",
            "]"
        ])
        return "\n".join(lines)

    def _extract_json_payload(self, text: str) -> Any:
        decoder = json.JSONDecoder()
        starts = [i for i, ch in enumerate(text) if ch in ["[", "{"]]
        for start in starts:
            snippet = text[start:].strip()
            try:
                obj, _ = decoder.raw_decode(snippet)
                if isinstance(obj, (list, dict)):
                    return obj
            except json.JSONDecodeError:
                continue
        return None

    def _fallback_orders(self, portfolio_state: PortfolioState) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for coin in self.trading_pairs:
            if self.fallback_mode == "de_risk" and coin in portfolio_state.positions:
                pos_size = abs(Decimal(str(portfolio_state.positions[coin]["size"])))
                out[coin] = {
                    "action": TradingAction.CLOSE_POSITION.value,
                    "size": pos_size,
                    "leverage": 1,
                    "confidence": Decimal("1"),
                    "reasoning": "Deterministic de-risk fallback"
                }
            else:
                out[coin] = {
                    "action": TradingAction.HOLD.value,
                    "size": Decimal("0"),
                    "leverage": 1,
                    "confidence": Decimal("0"),
                    "reasoning": "Deterministic hold fallback"
                }
        return out

    def _sanitize_orders(self, raw_data: Any) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}

        if isinstance(raw_data, dict):
            if all(isinstance(v, dict) for v in raw_data.values()):
                items = [{"coin": k, **v} for k, v in raw_data.items()]
            else:
                items = [raw_data]
        elif isinstance(raw_data, list):
            items = [item for item in raw_data if isinstance(item, dict)]
        else:
            items = []

        for item in items:
            coin = str(item.get("coin", "")).upper().strip()
            if coin not in self.trading_pairs:
                continue

            action = str(item.get("action", "hold")).strip().lower()
            if action not in self.allowed_actions:
                action = TradingAction.HOLD.value

            size = self._safe_decimal(item.get("size", 0))
            leverage = self._safe_decimal(item.get("leverage", 1))
            confidence = self._safe_decimal(item.get("confidence", 0))
            reasoning = str(item.get("reasoning", "No reasoning"))[:500]

            if leverage < Decimal("1"):
                leverage = Decimal("1")
            if leverage > self.hard_max_leverage:
                leverage = self.hard_max_leverage
            if confidence < Decimal("0"):
                confidence = Decimal("0")
            if confidence > Decimal("1"):
                confidence = Decimal("1")

            if action == TradingAction.HOLD.value:
                size = Decimal("0")

            if action in [TradingAction.BUY.value, TradingAction.SELL.value, TradingAction.INCREASE_POSITION.value]:
                min_size = self.min_size_by_coin.get(coin, Decimal("0"))
                if size < min_size:
                    action = TradingAction.HOLD.value
                    size = Decimal("0")

            normalized[coin] = {
                "action": action,
                "size": size,
                "leverage": int(leverage),
                "confidence": confidence,
                "reasoning": reasoning
            }

        return normalized

    def get_orders(
        self,
        market_data: Dict[str, Any],
        portfolio_state: PortfolioState
    ) -> Dict[str, Dict[str, Any]]:
        if not self.allow_external_llm:
            logger.info("External LLM disabled, using fallback strategy")
            return self._fallback_orders(portfolio_state)

        if not self.api_key:
            logger.error("OpenRouter API key missing, using fallback strategy")
            return self._fallback_orders(portfolio_state)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hyperliquid-bot.local",  # Optional: for OpenRouter analytics
            "X-Title": "Hyperliquid Trading Bot"  # Optional: for OpenRouter analytics
        }
        
        # Use Claude Opus 4.6 with reasoning enabled (extended thinking)
        payload = {
            "model": "anthropic/claude-3-opus-20240229",
            "messages": [
                {
                    "role": "user",
                    "content": self._build_prompt(market_data, portfolio_state)
                }
            ],
            "max_tokens": 4096,  # Increased for reasoning
            "temperature": 0.2,
            "stream": False,
            # Enable reasoning/extended thinking (Claude's extended reasoning feature)
            "extra_body": {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": 2000  # Allocate tokens for reasoning
                }
            }
        }

        try:
            response = self.session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60  # Increased timeout for reasoning
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenRouter request failed: {type(e).__name__}: {str(e)}")
            return self._fallback_orders(portfolio_state)

        if response.status_code != 200:
            logger.error(f"OpenRouter API error: status={response.status_code}, response={response.text[:200]}")
            return self._fallback_orders(portfolio_state)

        try:
            result = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenRouter response: {e}")
            return self._fallback_orders(portfolio_state)

        # Extract text from response - OpenRouter follows OpenAI format
        choices = result.get("choices", [])
        if not choices:
            logger.error("No choices in OpenRouter response")
            return self._fallback_orders(portfolio_state)
        
        message = choices[0].get("message", {})
        text = message.get("content", "")
        
        if not text:
            logger.error("Empty content in OpenRouter response")
            return self._fallback_orders(portfolio_state)

        parsed = self._extract_json_payload(text)
        if parsed is None:
            logger.warning("Failed to extract JSON from LLM response, using fallback")
            return self._fallback_orders(portfolio_state)

        sanitized = self._sanitize_orders(parsed)
        
        # Ensure all trading pairs have an order
        for coin in self.trading_pairs:
            if coin not in sanitized:
                sanitized[coin] = {
                    "action": TradingAction.HOLD.value,
                    "size": Decimal("0"),
                    "leverage": 1,
                    "confidence": Decimal("0"),
                    "reasoning": "No order for coin"
                }
        
        logger.info(f"LLM generated orders for {len(sanitized)} coins")
        return sanitized