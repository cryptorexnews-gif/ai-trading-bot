import json
import logging
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from llm.prompt_builder import LLMPromptBuilder
from models import MarketData, PortfolioState, TradingAction
from utils.decimals import to_decimal
from utils.retry import RETRYABLE_STATUS_CODES, retry_request

logger = logging.getLogger(__name__)


class LLMEngine:
    """
    LLM Engine using DeepSeek v3.2 via OpenRouter for trend trading decisions.
    All market data comes from Hyperliquid API; no external data sources.
    """

    REQUIRED_MODEL = "deepseek/deepseek-v3.2"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "deepseek/deepseek-v3.2",
        max_tokens: int = 8192,
        temperature: float = 0.2
    ):
        self.base_url = base_url

        requested_model = str(model or "").strip()
        if requested_model != self.REQUIRED_MODEL:
            logger.warning(
                f"LLM model '{requested_model}' non consentito: forzato a '{self.REQUIRED_MODEL}'"
            )
        self.model = self.REQUIRED_MODEL

        self.max_tokens = max_tokens
        self.temperature = temperature
        self.request_timeout = 90
        self.max_retries = 2

        self.prompt_builder = LLMPromptBuilder()

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/hyperliquid-trading-bot",
            "X-Title": "Hyperliquid Trading Bot"
        })
        logger.info(f"LLM Engine initialized with model={self.model}, timeout={self.request_timeout}s")

    def __repr__(self) -> str:
        return f"<LLMEngine model={self.model} base_url={self.base_url}>"

    def __str__(self) -> str:
        return self.__repr__()

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
            stop_loss_match = re.search(r'"stop_loss_pct"\s*:\s*(null|[\d.]+)', cleaned)
            take_profit_match = re.search(r'"take_profit_pct"\s*:\s*(null|[\d.]+)', cleaned)
            reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned)

            if action_match and size_match and leverage_match and confidence_match:
                stop_loss_pct = None
                take_profit_pct = None

                if stop_loss_match and stop_loss_match.group(1) != "null":
                    stop_loss_pct = float(stop_loss_match.group(1))
                if take_profit_match and take_profit_match.group(1) != "null":
                    take_profit_pct = float(take_profit_match.group(1))

                return {
                    "action": action_match.group(1),
                    "size": float(size_match.group(1)),
                    "leverage": int(leverage_match.group(1)),
                    "confidence": float(confidence_match.group(1)),
                    "stop_loss_pct": stop_loss_pct,
                    "take_profit_pct": take_profit_pct,
                    "reasoning": reasoning_match.group(1) if reasoning_match else "Extracted from partial response"
                }
        except (ValueError, AttributeError):
            pass

        logger.error(f"All JSON parse strategies failed. Response preview: {cleaned[:500]}...")
        return None

    def _coerce_int(self, value: Any, default: int, min_value: int, max_value: int) -> int:
        dec = to_decimal(value, Decimal(str(default)))
        coerced = int(dec)
        if coerced < min_value:
            return min_value
        if coerced > max_value:
            return max_value
        return coerced

    def _coerce_decimal(self, value: Any, default: Decimal, min_value: Decimal, max_value: Optional[Decimal] = None) -> Decimal:
        dec = to_decimal(value, default)
        if dec < min_value:
            dec = min_value
        if max_value is not None and dec > max_value:
            dec = max_value
        return dec

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
                "stop_loss_pct": None,
                "take_profit_pct": None,
                "reasoning": f"Original action '{action}' invalid, defaulting to hold."
            }

        confidence_dec = self._coerce_decimal(parsed.get("confidence"), Decimal("0"), Decimal("0"), Decimal("1"))
        confidence = float(confidence_dec)

        leverage = self._coerce_int(parsed.get("leverage"), default=1, min_value=1, max_value=50)

        size = self._coerce_decimal(parsed.get("size"), Decimal("0"), Decimal("0"))

        stop_loss_pct = None
        raw_sl = parsed.get("stop_loss_pct")
        if raw_sl is not None:
            sl = to_decimal(raw_sl, Decimal("-1"))
            if Decimal("0") < sl <= Decimal("1"):
                stop_loss_pct = sl

        take_profit_pct = None
        raw_tp = parsed.get("take_profit_pct")
        if raw_tp is not None:
            tp = to_decimal(raw_tp, Decimal("-1"))
            if Decimal("0") < tp <= Decimal("1"):
                take_profit_pct = tp

        return {
            "action": action,
            "size": size,
            "leverage": leverage,
            "confidence": confidence,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "reasoning": str(parsed.get("reasoning", "")),
        }

    def _call_openrouter(self, prompt: str) -> Optional[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": float(self.temperature),
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
        consecutive_losses: int = 0,
        managed_position: Optional[Dict[str, Any]] = None,
        protective_orders: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        prompt = self.prompt_builder.build_prompt(
            market_data=market_data,
            portfolio_state=portfolio_state,
            technical_data=technical_data,
            all_mids=all_mids,
            funding_data=funding_data,
            recent_trades=recent_trades,
            peak_portfolio_value=peak_portfolio_value,
            consecutive_losses=consecutive_losses,
            managed_position=managed_position,
            protective_orders=protective_orders,
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
            f"sl_pct={validated.get('stop_loss_pct')}, tp_pct={validated.get('take_profit_pct')}"
        )
        return validated