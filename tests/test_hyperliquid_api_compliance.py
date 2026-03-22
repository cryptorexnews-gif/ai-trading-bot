from decimal import Decimal
from unittest.mock import Mock, patch

from eth_account import Account
import requests

from api.helpers import post_hyperliquid_info
from config.bot_config import BotConfig
from exchange.transport import _raise_hyperliquid_http_error
from exchange_client import HyperliquidExchangeClient
from llm_engine import LLMEngine
from utils.data_fetcher import HyperliquidDataFetcher
from utils.hyperliquid_errors import AuthenticationError, ExchangeRejectedError, RateLimitError, UpstreamServerError


def test_llm_model_is_enforced_deepseek():
    assert BotConfig.REQUIRED_LLM_MODEL == "deepseek/deepseek-v3.2"
    assert LLMEngine.REQUIRED_MODEL == "deepseek/deepseek-v3.2"


def test_transport_error_mapping():
    try:
        _raise_hyperliquid_http_error(401, "/info")
        assert False, "Expected AuthenticationError"
    except AuthenticationError:
        pass

    try:
        _raise_hyperliquid_http_error(429, "/info")
        assert False, "Expected RateLimitError"
    except RateLimitError:
        pass

    try:
        _raise_hyperliquid_http_error(503, "/info")
        assert False, "Expected UpstreamServerError"
    except UpstreamServerError:
        pass

    try:
        _raise_hyperliquid_http_error(400, "/info")
        assert False, "Expected ExchangeRejectedError"
    except ExchangeRejectedError:
        pass


def test_post_hyperliquid_info_http_error_mapping_returns_none():
    mock_response = Mock()
    mock_response.status_code = 429
    http_error = requests.exceptions.HTTPError(response=mock_response)

    with patch("api.helpers.retry_request", side_effect=http_error):
        result = post_hyperliquid_info({"type": "allMids"}, timeout=5)
        assert result is None


def test_data_fetcher_batch_payload():
    fetcher = HyperliquidDataFetcher()
    captured = {"payload": None}

    def fake_post(payload, timeout=15):
        captured["payload"] = payload
        return [{"ok": True}]

    fetcher._post_info = fake_post  # noqa: SLF001
    out = fetcher.get_batch_info([{"type": "allMids"}, {"type": "meta"}], timeout=10)

    assert isinstance(out, list)
    assert len(out) == 1
    assert captured["payload"]["type"] == "batch"
    assert isinstance(captured["payload"]["requests"], list)
    assert len(captured["payload"]["requests"]) == 2


def test_exchange_client_open_orders_cache():
    private_key = Account.create().key.hex()
    client = HyperliquidExchangeClient(
        base_url="https://api.hyperliquid.xyz",
        private_key=private_key,
        enable_mainnet_trading=False,
        execution_mode="live",
    )

    calls = {"count": 0}

    def fake_post_info(payload, timeout=None):
        calls["count"] += 1
        return []

    client._post_info = fake_post_info  # noqa: SLF001

    first = client.get_open_orders("0xabc")
    second = client.get_open_orders("0xabc")
    third = client.get_open_orders("0xabc", force_refresh=True)

    assert isinstance(first, list)
    assert isinstance(second, list)
    assert isinstance(third, list)
    assert calls["count"] == 2, f"Expected 2 calls (cached + force refresh), got {calls['count']}"


def test_exchange_client_order_matcher_basic():
    private_key = Account.create().key.hex()
    client = HyperliquidExchangeClient(
        base_url="https://api.hyperliquid.xyz",
        private_key=private_key,
        enable_mainnet_trading=False,
        execution_mode="live",
    )

    order = {
        "coin": "BTC",
        "side": "sell",
        "sz": "0.0100",
        "triggerPx": "65000",
        "reduceOnly": True,
        "tpsl": "sl",
        "oid": 123,
    }

    matched = client._order_matches(  # noqa: SLF001
        order=order,
        coin="BTC",
        side="sell",
        size=Decimal("0.01"),
        trigger_price=Decimal("65000"),
        required_tpsl="sl",
    )
    assert matched is True


if __name__ == "__main__":
    import sys

    test_functions = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0

    for test_fn in test_functions:
        try:
            test_fn()
            passed += 1
            print(f"  ✅ {test_fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {test_fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  💥 {test_fn.__name__}: {type(e).__name__}: {e}")

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(1 if failed > 0 else 0)