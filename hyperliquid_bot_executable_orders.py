#!/usr/bin/env python3
"""
Hyperliquid Trading Bot con Órdenes Ejecutables
Versión endurecida de seguridad: validación estricta, logs sanitizados y guardas de ejecución.
"""

import os
import json
import time
import logging
import requests
import msgpack
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_typed_data
from Crypto.Hash import keccak

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/hyperliquid_bot_executable.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    from technical_analyzer_simple import technical_fetcher
except ImportError:
    technical_fetcher = None
    logger.warning("technical_analyzer_simple not available, using only zeroed market data")


class TradingAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE_POSITION = "close_position"
    INCREASE_POSITION = "increase_position"
    REDUCE_POSITION = "reduce_position"
    CHANGE_LEVERAGE = "change_leverage"


@dataclass
class MarketData:
    coin: str
    last_price: Decimal
    change_24h: Decimal
    volume_24h: Decimal
    funding_rate: Decimal
    timestamp: float


@dataclass
class PortfolioState:
    total_balance: Decimal
    available_balance: Decimal
    margin_usage: Decimal
    positions: Dict[str, Dict[str, Any]]


class HyperliquidTradingBotExecutable:
    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        deepseek_api_key: str,
        testnet: bool = False,
        trading_pairs: Optional[List[str]] = None
    ):
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.deepseek_api_key = deepseek_api_key
        self.testnet = testnet
        self.base_url = "https://api.hyperliquid.xyz"
        self.trading_pairs = trading_pairs or ["BTC", "ETH", "SOL", "BNB", "ADA"]

        self.position_size = Decimal('0.15')
        self.max_margin_usage = Decimal('0.95')
        self.min_balance = Decimal('0.01')

        self.max_order_margin_pct = Decimal(os.getenv("MAX_ORDER_MARGIN_PCT", "0.10"))
        self.hard_max_leverage = Decimal(os.getenv("HARD_MAX_LEVERAGE", "10"))
        self.min_confidence_open = Decimal(os.getenv("MIN_CONFIDENCE_OPEN", "0.20"))
        self.min_confidence_manage = Decimal(os.getenv("MIN_CONFIDENCE_MANAGE", "0.10"))

        self.enable_mainnet_trading = os.getenv("ENABLE_MAINNET_TRADING", "false").lower() == "true"

        self.allowed_actions = {action.value for action in TradingAction}
        self.min_size_by_coin: Dict[str, Decimal] = {
            "BTC": Decimal("0.001"),
            "ETH": Decimal("0.001"),
            "SOL": Decimal("0.1"),
            "BNB": Decimal("0.001"),
            "ADA": Decimal("16")
        }

        self.is_running = False
        self.last_analysis: Dict[str, Any] = {}

        derived_account = Account.from_key(self.private_key)
        if derived_account.address.lower() != self.wallet_address.lower():
            logger.error("Wallet address does not match private key derived address")
            raise ValueError("HYPERLIQUID_WALLET_ADDRESS does not match HYPERLIQUID_PRIVATE_KEY")
        logger.info(f"Bot initialized for wallet {self._mask_wallet(self.wallet_address)}")
        logger.info(f"Trading pairs: {self.trading_pairs}")

        if not self.testnet and not self.enable_mainnet_trading:
            logger.warning("Mainnet live execution is DISABLED. Set ENABLE_MAINNET_TRADING=true to enable real orders.")

    def _mask_wallet(self, wallet: str) -> str:
        if not wallet or len(wallet) < 12:
            return "invalid_wallet"
        return f"{wallet[:6]}...{wallet[-4:]}"

    def _safe_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return default

    def get_all_market_data(self) -> Dict[str, MarketData]:
        market_data: Dict[str, MarketData] = {}

        for coin in self.trading_pairs:
            if technical_fetcher is None:
                market_data[coin] = MarketData(
                    coin=coin,
                    last_price=Decimal("0"),
                    change_24h=Decimal("0"),
                    volume_24h=Decimal("0"),
                    funding_rate=Decimal("0"),
                    timestamp=time.time()
                )
                continue

            indicators = technical_fetcher.get_technical_indicators(coin)
            if indicators and self._safe_decimal(indicators.get('current_price', 0)) > Decimal("0"):
                market_data[coin] = MarketData(
                    coin=coin,
                    last_price=self._safe_decimal(indicators.get('current_price', 0)),
                    change_24h=self._safe_decimal(indicators.get('change_24h', 0)),
                    volume_24h=self._safe_decimal(indicators.get('volume_24h', 0)),
                    funding_rate=Decimal("0.0001"),
                    timestamp=time.time()
                )
            else:
                logger.error(f"No real market data for {coin}; skipping trading for this coin this cycle")
                market_data[coin] = MarketData(
                    coin=coin,
                    last_price=Decimal("0"),
                    change_24h=Decimal("0"),
                    volume_24h=Decimal("0"),
                    funding_rate=Decimal("0"),
                    timestamp=time.time()
                )

        return market_data

    def get_portfolio_state(self) -> PortfolioState:
        payload = {"type": "clearinghouseState", "user": self.wallet_address}
        response = requests.post(f"{self.base_url}/info", json=payload, timeout=15)

        if response.status_code != 200:
            logger.error(f"Could not fetch portfolio state: {response.status_code} - {response.text}")
            return PortfolioState(Decimal("0"), Decimal("0"), Decimal("0"), {})

        data = response.json()
        margin_summary = data.get("marginSummary", {})
        total_balance = self._safe_decimal(margin_summary.get("accountValue", 0))
        available_balance = self._safe_decimal(data.get("withdrawable", 0))
        total_margin_used = self._safe_decimal(margin_summary.get("totalMarginUsed", 0))
        margin_usage = (total_margin_used / total_balance) if total_balance > 0 else Decimal("0")

        positions: Dict[str, Dict[str, Any]] = {}
        for position in data.get("assetPositions", []):
            p = position.get("position", {})
            coin = p.get("coin", "")
            if not coin:
                continue

            size = self._safe_decimal(p.get("szi", 0))
            if size == 0:
                continue

            entry_price = self._safe_decimal(p.get("entryPx", 0))
            unrealized_pnl = self._safe_decimal(p.get("unrealizedPnl", 0))
            margin_used = self._safe_decimal(p.get("marginUsed", 0))
            leverage_data = p.get("leverage", {})
            leverage = self._safe_decimal(leverage_data.get("value", 1)) if leverage_data else Decimal("1")

            position_value = abs(size * entry_price)
            calculated_leverage = (position_value / margin_used) if margin_used > 0 else leverage

            positions[coin] = {
                "size": size,
                "entry_price": entry_price,
                "unrealized_pnl": unrealized_pnl,
                "margin_used": margin_used,
                "leverage": calculated_leverage,
                "position_value": position_value
            }

        long_count = sum(1 for _, pos in positions.items() if pos["size"] > 0)
        short_count = sum(1 for _, pos in positions.items() if pos["size"] < 0)
        logger.info(
            f"Portfolio snapshot | total=${total_balance:.2f} available=${available_balance:.2f} "
            f"margin={margin_usage*100:.1f}% positions={len(positions)} (L:{long_count}/S:{short_count})"
        )

        return PortfolioState(
            total_balance=total_balance,
            available_balance=available_balance,
            margin_usage=margin_usage,
            positions=positions
        )

    def _build_sanitized_prompt(
        self,
        market_data: Dict[str, MarketData],
        portfolio_state: PortfolioState
    ) -> str:
        balance_bucket = "low" if portfolio_state.total_balance < Decimal("100") else "medium" if portfolio_state.total_balance < Decimal("10000") else "high"
        margin_pct = (portfolio_state.margin_usage * Decimal("100")).quantize(Decimal("0.1"))
        position_count = len(portfolio_state.positions)
        long_count = sum(1 for _, p in portfolio_state.positions.items() if p["size"] > 0)
        short_count = sum(1 for _, p in portfolio_state.positions.items() if p["size"] < 0)

        prompt_lines = [
            "You are an expert cryptocurrency trading analyst.",
            "Return ONLY valid JSON array with one object per coin.",
            "",
            "PORTFOLIO CONTEXT (SANITIZED):",
            f"- Balance tier: {balance_bucket}",
            f"- Margin usage: {margin_pct}%",
            f"- Open positions: {position_count} (long: {long_count}, short: {short_count})",
            "",
            "MARKET DATA:"
        ]

        for coin, data in market_data.items():
            prompt_lines.append(
                f"- {coin}: price={data.last_price}, change_24h={data.change_24h}, volume_24h={data.volume_24h}"
            )

        prompt_lines.extend([
            "",
            "ACTION values must be one of:",
            "buy, sell, hold, close_position, increase_position, reduce_position, change_leverage",
            "",
            "Size minimums:",
            "BTC:0.001 ETH:0.001 SOL:0.1 BNB:0.001 ADA:16",
            "",
            "Return format example:",
            "[",
            "{\"coin\":\"BTC\",\"action\":\"hold\",\"size\":0,\"leverage\":1,\"confidence\":0.5,\"reasoning\":\"...\"}",
            "]"
        ])

        return "\n".join(prompt_lines)

    def _extract_json_payload(self, text: str) -> Optional[Any]:
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

    def _sanitize_and_validate_orders(self, raw_data: Any) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}

        items: List[Dict[str, Any]]
        if isinstance(raw_data, dict):
            if all(isinstance(v, dict) for v in raw_data.values()):
                items = [{"coin": k, **v} for k, v in raw_data.items()]
            else:
                items = [raw_data]
        elif isinstance(raw_data, list):
            items = [item for item in raw_data if isinstance(item, dict)]
        else:
            return normalized

        for item in items:
            coin = str(item.get("coin", "")).upper().strip()
            if coin not in self.trading_pairs:
                continue

            action = str(item.get("action", "hold")).strip().lower()
            if action not in self.allowed_actions:
                logger.warning(f"Rejected unknown action '{action}' for {coin}; defaulting to hold")
                action = TradingAction.HOLD.value

            size = self._safe_decimal(item.get("size", 0))
            leverage = self._safe_decimal(item.get("leverage", 1))
            confidence = self._safe_decimal(item.get("confidence", 0))
            reasoning = str(item.get("reasoning", "No reasoning provided"))[:500]

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
                    logger.warning(f"Order size for {coin} below min ({size} < {min_size}); switching to hold")
                    action = TradingAction.HOLD.value
                    size = Decimal("0")

            normalized[coin] = {
                "action": action,
                "size": size,
                "leverage": int(leverage),
                "confidence": confidence,
                "reasoning": reasoning
            }

        for coin in self.trading_pairs:
            if coin not in normalized:
                normalized[coin] = {
                    "action": TradingAction.HOLD.value,
                    "size": Decimal("0"),
                    "leverage": 1,
                    "confidence": Decimal("0"),
                    "reasoning": "No order received for this coin"
                }

        return normalized

    def get_executable_orders_from_llm(
        self,
        market_data: Dict[str, MarketData],
        portfolio_state: PortfolioState
    ) -> Dict[str, Dict[str, Any]]:
        prompt = self._build_sanitized_prompt(market_data, portfolio_state)

        headers = {
            "Authorization": f"Bearer {self.deepseek_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "Return valid JSON only. Do not include markdown."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2,
            "max_tokens": 1400
        }

        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            logger.warning(f"DeepSeek API failed ({response.status_code}), using safe fallback")
            return self._sanitize_and_validate_orders([])

        result = response.json()
        analysis_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        json_data = self._extract_json_payload(analysis_text)
        if json_data is None:
            logger.warning("DeepSeek response did not contain valid JSON, using safe fallback")
            return self._sanitize_and_validate_orders([])

        orders = self._sanitize_and_validate_orders(json_data)
        for coin, order in orders.items():
            logger.info(
                f"Order {coin}: {order['action']} size={order['size']} lev={order['leverage']} conf={order['confidence']}"
            )
        return orders

    def risk_management_check(
        self,
        order: Dict[str, Any],
        portfolio_state: PortfolioState,
        coin: str,
        market_price: Decimal
    ) -> bool:
        action = order.get("action", "").strip().lower()
        size = self._safe_decimal(order.get("size", 0))
        leverage = self._safe_decimal(order.get("leverage", 1))
        confidence = self._safe_decimal(order.get("confidence", 0))

        if action not in self.allowed_actions:
            logger.warning(f"Risk check rejected unknown action for {coin}: {action}")
            return False

        if action == TradingAction.HOLD.value:
            return True

        if leverage < Decimal("1") or leverage > self.hard_max_leverage:
            logger.warning(f"Risk check rejected leverage for {coin}: {leverage}")
            return False

        if action in [TradingAction.CLOSE_POSITION.value, TradingAction.REDUCE_POSITION.value, TradingAction.CHANGE_LEVERAGE.value]:
            return confidence >= self.min_confidence_manage

        if confidence < self.min_confidence_open:
            logger.warning(f"Risk check rejected {coin}: confidence too low ({confidence})")
            return False

        if portfolio_state.margin_usage > self.max_margin_usage:
            logger.warning(f"Risk check rejected {coin}: margin usage too high ({portfolio_state.margin_usage*100:.1f}%)")
            return False

        if market_price <= 0 or size <= 0:
            logger.warning(f"Risk check rejected {coin}: invalid market price or size")
            return False

        required_margin = (size * market_price) / leverage
        max_margin_per_trade = portfolio_state.total_balance * self.max_order_margin_pct

        if required_margin > portfolio_state.available_balance:
            logger.warning(
                f"Risk check rejected {coin}: required margin {required_margin:.4f} > available {portfolio_state.available_balance:.4f}"
            )
            return False

        if required_margin > max_margin_per_trade:
            logger.warning(
                f"Risk check rejected {coin}: required margin {required_margin:.4f} > cap per trade {max_margin_per_trade:.4f}"
            )
            return False

        return True

    def execute_executable_order(self, coin: str, order: Dict[str, Any], market_data: MarketData) -> bool:
        portfolio_state = self.get_portfolio_state()

        action = order.get("action", "").strip().lower()
        size = self._safe_decimal(order.get("size", 0))
        leverage = int(order.get("leverage", 1))
        confidence = self._safe_decimal(order.get("confidence", 0))
        reasoning = order.get("reasoning", "")

        if action not in self.allowed_actions:
            logger.warning(f"Skipping unknown action for {coin}: {action}")
            return False

        logger.info(f"Executing order {coin}: {action} size={size} lev={leverage} conf={confidence}")
        logger.info(f"Reason: {reasoning}")

        if action == TradingAction.HOLD.value:
            return False

        if action == TradingAction.CLOSE_POSITION.value and coin in portfolio_state.positions:
            existing_position = portfolio_state.positions[coin]
            close_size = abs(existing_position["size"])
            side = "sell" if existing_position["size"] > 0 else "buy"
            return self.execute_real_order(coin, side, close_size, market_data.last_price)

        if action == TradingAction.REDUCE_POSITION.value and coin in portfolio_state.positions:
            existing_position = portfolio_state.positions[coin]
            current_size = abs(existing_position["size"])
            reduce_size = size if size <= current_size else current_size
            side = "sell" if existing_position["size"] > 0 else "buy"
            return self.execute_real_order(coin, side, reduce_size, market_data.last_price)

        if action == TradingAction.CHANGE_LEVERAGE.value and coin in portfolio_state.positions:
            return self.set_leverage(coin, leverage)

        if action == TradingAction.INCREASE_POSITION.value and coin in portfolio_state.positions:
            existing_position = portfolio_state.positions[coin]
            side = "buy" if existing_position["size"] > 0 else "sell"
            leverage_ok = self.set_leverage(coin, leverage)
            if not leverage_ok:
                return False
            return self.execute_real_order(coin, side, size, market_data.last_price)

        if action in [TradingAction.BUY.value, TradingAction.SELL.value]:
            side = "buy" if action == TradingAction.BUY.value else "sell"
            leverage_ok = self.set_leverage(coin, leverage)
            if not leverage_ok:
                return False
            return self.execute_real_order(coin, side, size, market_data.last_price)

        logger.warning(f"No execution path matched for {coin} action={action}")
        return False

    def run_trading_cycle(self):
        logger.info("Starting trading cycle")
        portfolio_state = self.get_portfolio_state()
        all_market_data = self.get_all_market_data()
        executable_orders = self.get_executable_orders_from_llm(all_market_data, portfolio_state)

        trades_executed: List[str] = []
        hold_decisions: List[str] = []
        failed_checks: List[str] = []

        for coin in self.trading_pairs:
            order = executable_orders.get(coin, {})
            market_data = all_market_data.get(coin)
            if not market_data or market_data.last_price <= 0:
                failed_checks.append(f"{coin}: no market data")
                continue

            if not self.risk_management_check(order, portfolio_state, coin, market_data.last_price):
                failed_checks.append(f"{coin}: risk check failed")
                continue

            action = order.get("action", "hold")
            if action == TradingAction.HOLD.value:
                hold_decisions.append(coin)
                continue

            success = self.execute_executable_order(coin, order, market_data)
            if success:
                trades_executed.append(f"{coin}:{action}")
            else:
                failed_checks.append(f"{coin}: execution failed")

        self._print_cycle_summary(portfolio_state, trades_executed, hold_decisions, failed_checks)

    def start(self, cycle_interval: int = 300):
        self.is_running = True
        logger.info(f"Starting bot (interval={cycle_interval}s)")

        while self.is_running:
            self.run_trading_cycle()
            logger.info(f"Sleeping {cycle_interval}s before next cycle")
            time.sleep(cycle_interval)

    def _print_cycle_summary(
        self,
        portfolio_state: PortfolioState,
        trades_executed: List[str],
        hold_decisions: List[str],
        failed_checks: List[str]
    ):
        print("\n" + "=" * 80)
        print("CYCLE SUMMARY - Executable Orders Strategy")
        print("=" * 80)
        print(
            f"Portfolio value ${portfolio_state.total_balance:.2f} | "
            f"Available ${portfolio_state.available_balance:.2f} | "
            f"Margin {portfolio_state.margin_usage*100:.1f}%"
        )
        print(f"Executed trades: {', '.join(trades_executed) if trades_executed else 'none'}")
        print(f"Hold decisions: {', '.join(hold_decisions) if hold_decisions else 'none'}")
        print(f"Skipped/failed: {', '.join(failed_checks) if failed_checks else 'none'}")
        print("=" * 80 + "\n")

    def sign_l1_action_exact(self, action: Dict[str, Any], vault_address: Optional[str], nonce: int, expires_after: Optional[int], is_mainnet: bool = True) -> Dict[str, Any]:
        def address_to_bytes(address: str) -> bytes:
            return bytes.fromhex(address[2:].lower())

        def action_hash(action_payload: Dict[str, Any], vault_addr: Optional[str], n: int, exp_after: Optional[int]) -> bytes:
            data = msgpack.packb(action_payload)
            data += n.to_bytes(8, "big")
            if vault_addr is None:
                data += b"\x00"
            else:
                data += b"\x01"
                data += address_to_bytes(vault_addr)
            if exp_after is not None:
                data += b"\x00"
                data += exp_after.to_bytes(8, "big")
            return keccak.new(data=data, digest_bits=256).digest()

        def construct_phantom_agent(hash_bytes: bytes, mainnet: bool = True) -> Dict[str, str]:
            return {
                "source": "a" if mainnet else "b",
                "connectionId": "0x" + hash_bytes.hex()
            }

        def l1_payload(phantom_agent: Dict[str, str]) -> Dict[str, Any]:
            return {
                "domain": {
                    "chainId": 1337,
                    "name": "Exchange",
                    "verifyingContract": "0x0000000000000000000000000000000000000000",
                    "version": "1",
                },
                "types": {
                    "Agent": [
                        {"name": "source", "type": "string"},
                        {"name": "connectionId", "type": "bytes32"},
                    ],
                    "EIP712Domain": [
                        {"name": "name", "type": "string"},
                        {"name": "version", "type": "string"},
                        {"name": "chainId", "type": "uint256"},
                        {"name": "verifyingContract", "type": "address"},
                    ],
                },
                "primaryType": "Agent",
                "message": phantom_agent,
            }

        account = Account.from_key(self.private_key)
        hash_bytes = action_hash(action, vault_address, nonce, expires_after)
        phantom_agent = construct_phantom_agent(hash_bytes, is_mainnet)
        data = l1_payload(phantom_agent)

        structured_data = encode_typed_data(full_message=data)
        signed = account.sign_message(structured_data)

        return {"r": hex(signed.r), "s": hex(signed.s), "v": signed.v}

    def execute_real_order(self, coin: str, side: str, size: Decimal, price: Decimal) -> bool:
        if not self.testnet and not self.enable_mainnet_trading:
            logger.warning(f"DRY-RUN: blocked live {side.upper()} order for {coin} size={size} price={price}")
            return True

        asset_id = self._get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Could not find asset ID for {coin}")
            return False

        is_buy = side.lower() == "buy"

        reference_price = price
        meta_payload = {"type": "meta"}
        meta_resp = requests.post(f"{self.base_url}/info", json=meta_payload, timeout=15)
        if meta_resp.status_code == 200:
            data = meta_resp.json()
            for asset in data.get("universe", []):
                if asset.get("name") == coin and asset.get("markPx") is not None:
                    reference_price = self._safe_decimal(asset.get("markPx"))
                    break

        max_deviation = reference_price * Decimal("0.05")
        if is_buy:
            limit_price = min(price, reference_price + (max_deviation * Decimal("0.5")))
        else:
            limit_price = max(price, reference_price - (max_deviation * Decimal("0.5")))
        lower_bound = reference_price - max_deviation
        upper_bound = reference_price + max_deviation
        if limit_price < lower_bound:
            limit_price = lower_bound
        if limit_price > upper_bound:
            limit_price = upper_bound

        tick_size, precision = self._get_tick_size_and_precision(asset_id)
        if tick_size <= 0:
            tick_size = Decimal("0.01")
            precision = 2

        rounded_ticks = (limit_price / tick_size).quantize(Decimal("1"))
        limit_price = rounded_ticks * tick_size
        quantizer = Decimal("1").scaleb(-precision)
        limit_price = limit_price.quantize(quantizer)

        if coin == "ADA":
            size_str = str(int(size))
        else:
            size_str = str(size.normalize())

        order_wire = {
            "a": asset_id,
            "b": is_buy,
            "p": str(limit_price),
            "s": size_str,
            "r": False,
            "t": {"limit": {"tif": "Gtc"}}
        }

        action = {
            "type": "order",
            "orders": [order_wire],
            "grouping": "na"
        }

        nonce = int(time.time() * 1000)
        signature = self.sign_l1_action_exact(
            action=action,
            vault_address=None,
            nonce=nonce,
            expires_after=None,
            is_mainnet=True
        )

        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None
        }

        logger.info(f"Sending order: {coin} {side.upper()} size={size_str} limit={limit_price}")

        response = requests.post(
            f"{self.base_url}/exchange",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15
        )

        if response.status_code != 200:
            logger.error(f"Order HTTP error: {response.status_code} - {response.text}")
            return False

        result = response.json()
        if result.get("status") != "ok":
            logger.error(f"Order rejected: {result}")
            return False

        statuses = result.get("response", {}).get("data", {}).get("statuses", [])
        for status in statuses:
            if "error" in status:
                logger.error(f"Order error for {coin}: {status['error']}")
                return False

        logger.info(f"Order success for {coin}")
        return True

    def set_leverage(self, coin: str, leverage: int) -> bool:
        if leverage < 1:
            leverage = 1
        if Decimal(str(leverage)) > self.hard_max_leverage:
            leverage = int(self.hard_max_leverage)

        if not self.testnet and not self.enable_mainnet_trading:
            logger.warning(f"DRY-RUN: blocked leverage update for {coin} -> {leverage}x")
            return True

        asset_id = self._get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Could not find asset ID for {coin}")
            return False

        max_leverage = self._get_max_leverage(coin)
        if leverage > max_leverage:
            leverage = max_leverage

        action = {
            "type": "updateLeverage",
            "asset": asset_id,
            "isCross": True,
            "leverage": leverage
        }

        nonce = int(time.time() * 1000)
        signature = self.sign_l1_action_exact(
            action=action,
            vault_address=None,
            nonce=nonce,
            expires_after=None,
            is_mainnet=True
        )

        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None
        }

        response = requests.post(
            f"{self.base_url}/exchange",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        if response.status_code != 200:
            logger.error(f"Leverage HTTP error: {response.status_code} - {response.text}")
            return False

        result = response.json()
        if result.get("status") == "ok":
            logger.info(f"Leverage set for {coin}: {leverage}x")
            return True

        logger.error(f"Failed to set leverage for {coin}: {result}")
        return False

    def _get_asset_id(self, coin: str) -> Optional[int]:
        payload = {"type": "meta"}
        response = requests.post(f"{self.base_url}/info", json=payload, timeout=15)
        if response.status_code != 200:
            logger.error(f"Failed to get meta for asset IDs: {response.status_code}")
            return None

        data = response.json()
        for index, asset in enumerate(data.get("universe", [])):
            if asset.get("name") == coin:
                return index
        return None

    def _get_tick_size_and_precision(self, asset_id: int) -> Tuple[Decimal, int]:
        payload = {"type": "allMids"}
        response = requests.post(f"{self.base_url}/info", json=payload, timeout=15)
        if response.status_code == 200:
            market_data = response.json()
            meta_resp = requests.post(f"{self.base_url}/info", json={"type": "meta"}, timeout=15)
            if meta_resp.status_code == 200:
                universe = meta_resp.json().get("universe", [])
                if 0 <= asset_id < len(universe):
                    coin = universe[asset_id].get("name", "")
                    raw_price = str(market_data.get(coin, "0"))
                    if "." in raw_price:
                        decimals = len(raw_price.rstrip("0").split(".")[1]) if raw_price.rstrip("0").split(".")[1] else 0
                    else:
                        decimals = 0
                    tick_size = Decimal("1").scaleb(-decimals) if decimals > 0 else Decimal("1")
                    return tick_size, decimals

        default_tick_sizes: Dict[int, Tuple[Decimal, int]] = {
            0: (Decimal("0.1"), 1),       # BTC
            1: (Decimal("0.01"), 2),      # ETH
            5: (Decimal("0.001"), 3),     # SOL
            7: (Decimal("0.01"), 2),      # BNB
            65: (Decimal("0.00001"), 5)   # ADA
        }
        return default_tick_sizes.get(asset_id, (Decimal("0.01"), 2))

    def _get_max_leverage(self, coin: str) -> int:
        payload = {"type": "meta"}
        response = requests.post(f"{self.base_url}/info", json=payload, timeout=15)
        if response.status_code != 200:
            return 10

        data = response.json()
        for asset in data.get("universe", []):
            if asset.get("name") == coin:
                return int(asset.get("maxLeverage", 10))
        return 10

    def stop(self):
        self.is_running = False
        logger.info("Stopping bot")


def main():
    import sys

    wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

    if not all([wallet_address, private_key, deepseek_api_key]):
        logger.error("Missing required environment variables")
        return

    bot = HyperliquidTradingBotExecutable(
        wallet_address=wallet_address,
        private_key=private_key,
        deepseek_api_key=deepseek_api_key,
        testnet=False,
        trading_pairs=["BTC", "ETH", "SOL", "BNB", "ADA"]
    )

    if len(sys.argv) > 1 and sys.argv[1] == "--single-cycle":
        logger.info("Executing single cycle mode")
        bot.run_trading_cycle()
        logger.info("Single cycle completed")
    else:
        try:
            bot.start(cycle_interval=300)
        except KeyboardInterrupt:
            bot.stop()


if __name__ == "__main__":
    main()