import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import msgpack
import requests
from Crypto.Hash import keccak
from eth_account import Account
from eth_account.messages import encode_typed_data

from utils.circuit_breaker import CircuitBreakerOpenError, get_or_create_circuit_breaker
from utils.decimals import safe_decimal
from utils.http import create_robust_session

logger = logging.getLogger(__name__)


class HyperliquidExchangeClient:
    """
    Client for Hyperliquid exchange API.
    Handles order signing (EIP-712), placement, leverage, and market data.
    Supports both live and paper trading modes.

    Security: The raw private key is never stored. Only the derived Account object
    is kept in memory. __repr__ is overridden to prevent accidental secret leakage.
    """

    def __init__(
        self,
        base_url: str,
        private_key: str,
        enable_mainnet_trading: bool = False,
        execution_mode: str = "paper",
        meta_cache_ttl_sec: int = 120,
        paper_slippage_bps: Decimal = Decimal("5"),
        info_timeout: int = 15,
        exchange_timeout: int = 30,
    ):
        self.base_url = base_url
        self.enable_mainnet_trading = enable_mainnet_trading
        self.execution_mode = execution_mode
        self.meta_cache_ttl_sec = meta_cache_ttl_sec
        self.paper_slippage_bps = paper_slippage_bps
        self.info_timeout = info_timeout
        self.exchange_timeout = exchange_timeout

        self.session = create_robust_session()

        self.account = Account.from_key(private_key)

        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_at = 0.0
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at = 0.0
        self._mids_cache_ttl = 30

        self._info_cb = get_or_create_circuit_breaker(
            "hyperliquid_info", failure_threshold=5, recovery_timeout=30.0
        )
        self._exchange_cb = get_or_create_circuit_breaker(
            "hyperliquid_exchange", failure_threshold=3, recovery_timeout=60.0
        )

        logger.info(
            f"Exchange client initialized: base_url={self.base_url}, "
            f"mode={self.execution_mode}, mainnet={self.enable_mainnet_trading}, "
            f"wallet={self.get_wallet_address_masked()}"
        )

    def __repr__(self) -> str:
        return (
            f"<HyperliquidExchangeClient base_url={self.base_url} "
            f"mode={self.execution_mode} wallet={self.get_wallet_address_masked()}>"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def get_derived_address(self) -> str:
        return self.account.address

    def get_wallet_address_masked(self) -> str:
        addr = self.account.address
        if not addr or len(addr) < 12:
            return "invalid"
        return f"{addr[:6]}...{addr[-4:]}"

    @staticmethod
    def validate_wallet_address(private_key: str, expected_address: str) -> bool:
        derived = Account.from_key(private_key).address
        return derived.lower() == expected_address.lower()

    def _post_info(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        if timeout is None:
            timeout = self.info_timeout

        def _do_post():
            response = self.session.post(f"{self.base_url}/info", json=payload, timeout=timeout)
            if response.status_code != 200:
                logger.error(f"/info type={payload.get('type', 'unknown')} failed status={response.status_code}")
                response.raise_for_status()
            return response.json()

        try:
            return self._info_cb.call(_do_post)
        except CircuitBreakerOpenError:
            logger.error("Circuit breaker OPEN for /info endpoint")
            return None
        except requests.exceptions.Timeout:
            logger.error(f"/info timeout after {timeout}s for type={payload.get('type', 'unknown')}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"/info connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"/info unexpected error: {type(e).__name__}: {str(e)}")
            return None

    def _post_exchange(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        if timeout is None:
            timeout = self.exchange_timeout

        def _do_post():
            response = self.session.post(
                f"{self.base_url}/exchange",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout
            )
            if response.status_code != 200:
                logger.error(f"/exchange failed status={response.status_code}")
                response.raise_for_status()
            return response.json()

        try:
            return self._exchange_cb.call(_do_post)
        except CircuitBreakerOpenError:
            logger.error("Circuit breaker OPEN for /exchange endpoint")
            return None
        except requests.exceptions.Timeout:
            logger.error(f"/exchange timeout after {timeout}s")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"/exchange connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"/exchange unexpected error: {type(e).__name__}: {str(e)}")
            return None

    def get_meta(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        now = time.time()
        if not force_refresh and self._meta_cache and (now - self._meta_cache_at) < self.meta_cache_ttl_sec:
            return self._meta_cache
        meta = self._post_info({"type": "meta"})
        if meta is None:
            return self._meta_cache
        self._meta_cache = meta
        self._meta_cache_at = now
        return meta

    def get_all_mids(self, force_refresh: bool = False) -> Optional[Dict[str, str]]:
        now = time.time()
        if not force_refresh and self._mids_cache and (now - self._mids_cache_at) < self._mids_cache_ttl:
            return self._mids_cache
        mids = self._post_info({"type": "allMids"})
        if mids is None:
            return self._mids_cache
        self._mids_cache = mids
        self._mids_cache_at = now
        return mids

    def get_user_state(self, user: str) -> Optional[Dict[str, Any]]:
        return self._post_info({"type": "clearinghouseState", "user": user})

    def get_asset_id(self, coin: str) -> Optional[int]:
        meta = self.get_meta(force_refresh=False)
        if meta is None:
            return None
        for index, asset in enumerate(meta.get("universe", [])):
            if asset.get("name") == coin:
                return index
        return None

    def get_max_leverage(self, coin: str) -> int:
        meta = self.get_meta(force_refresh=False)
        if meta is None:
            return 10
        for asset in meta.get("universe", []):
            if asset.get("name") == coin:
                return int(asset.get("maxLeverage", 10))
        return 10

    def get_sz_decimals(self, coin: str) -> Optional[int]:
        meta = self.get_meta(force_refresh=False)
        if meta is None:
            return None
        for asset in meta.get("universe", []):
            if asset.get("name") == coin:
                return asset.get("szDecimals")
        return None

    def get_reference_price(self, coin: str, fallback_price: Decimal) -> Decimal:
        mids = self.get_all_mids()
        if mids and coin in mids:
            mid_price = safe_decimal(mids[coin], Decimal("0"))
            if mid_price > 0:
                return mid_price
        return fallback_price

    def get_tick_size_and_precision(self, asset_id: int) -> Tuple[Decimal, int]:
        meta = self.get_meta(force_refresh=False)
        if meta is None:
            return (Decimal("0.01"), 2)

        universe = meta.get("universe", [])
        if not (0 <= asset_id < len(universe)):
            return (Decimal("0.01"), 2)

        coin = universe[asset_id].get("name", "")
        mids = self.get_all_mids()

        if mids is not None and coin in mids:
            raw_price = str(mids.get(coin, "0"))
            if "." in raw_price:
                right_side = raw_price.rstrip("0").split(".")[1]
                decimals = len(right_side) if right_side else 0
            else:
                decimals = 0

            decimals = max(1, min(decimals, 8))
            tick_size = Decimal("1").scaleb(-decimals) if decimals > 0 else Decimal("1")
            return tick_size, decimals

        default_tick_sizes: Dict[int, Tuple[Decimal, int]] = {
            0: (Decimal("0.1"), 1), 1: (Decimal("0.01"), 2),
            5: (Decimal("0.001"), 3), 7: (Decimal("0.01"), 2),
            65: (Decimal("0.00001"), 5)
        }
        return default_tick_sizes.get(asset_id, (Decimal("0.01"), 2))

    def _address_to_bytes(self, address: str) -> bytes:
        return bytes.fromhex(address[2:].lower())

    def _action_hash(self, action: Dict[str, Any], vault_address: Optional[str], nonce: int, expires_after: Optional[int]) -> bytes:
        data = msgpack.packb(action)
        data += nonce.to_bytes(8, "big")
        if vault_address is None:
            data += b"\x00"
        else:
            data += b"\x01"
            data += self._address_to_bytes(vault_address)
        if expires_after is not None:
            data += b"\x00"
            data += expires_after.to_bytes(8, "big")
        return keccak.new(data=data, digest_bits=256).digest()

    def _l1_payload(self, phantom_agent: Dict[str, str]) -> Dict[str, Any]:
        return {
            "domain": {
                "chainId": 1337,
                "name": "Exchange",
                "verifyingContract": "0x0000000000000000000000000000000000000000",
                "version": "1",
            },
            "types": {
                "Agent": [{"name": "source", "type": "string"}, {"name": "connectionId", "type": "bytes32"}],
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

    def sign_l1_action_exact(self, action: Dict[str, Any], vault_address: Optional[str], nonce: int, expires_after: Optional[int], is_mainnet: bool = True) -> Dict[str, Any]:
        hash_bytes = self._action_hash(action, vault_address, nonce, expires_after)
        phantom_agent = {"source": "a" if is_mainnet else "b", "connectionId": "0x" + hash_bytes.hex()}
        data = self._l1_payload(phantom_agent)
        structured_data = encode_typed_data(full_message=data)
        signed = self.account.sign_message(structured_data)
        return {"r": hex(signed.r), "s": hex(signed.s), "v": signed.v}

    def _extract_order_ids(self, exchange_result: Dict[str, Any]) -> List[int]:
        ids: List[int] = []
        statuses = exchange_result.get("response", {}).get("data", {}).get("statuses", [])
        for status in statuses:
            resting = status.get("resting", {})
            oid = resting.get("oid")
            if oid is not None:
                ids.append(int(oid))
        return ids

    def set_leverage(self, coin: str, leverage: int) -> bool:
        leverage = max(1, leverage)
        max_leverage = self.get_max_leverage(coin)
        if leverage > max_leverage:
            leverage = max_leverage

        if self.execution_mode != "live" or not self.enable_mainnet_trading:
            logger.info(f"PAPER leverage set {coin} -> {leverage}x")
            return True

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for {coin}")
            return False

        action = {"type": "updateLeverage", "asset": asset_id, "isCross": True, "leverage": leverage}
        nonce = int(time.time() * 1000)
        signature = self.sign_l1_action_exact(action, None, nonce, None, True)
        payload = {"action": action, "nonce": nonce, "signature": signature, "vaultAddress": None}

        result = self._post_exchange(payload)
        if result is None:
            return False
        if result.get("status") == "ok":
            logger.info(f"LIVE leverage set {coin} -> {leverage}x")
            return True
        logger.error(f"Set leverage failed for {coin}: {result}")
        return False

    def place_order(self, coin: str, side: str, size: Decimal, desired_price: Decimal) -> Dict[str, Any]:
        if self.execution_mode != "live" or not self.enable_mainnet_trading:
            slip = (self.paper_slippage_bps / Decimal("10000"))
            fill_price = desired_price * (Decimal("1") + slip) if side.lower() == "buy" else desired_price * (Decimal("1") - slip)
            notional = abs(size * fill_price)
            logger.info(f"PAPER order {coin} {side.upper()} size={size} fill={fill_price}")
            return {"success": True, "mode": "paper", "filled_price": str(fill_price), "notional": str(notional)}

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for {coin}")
            return {"success": False, "mode": "live", "reason": "asset_not_found", "notional": "0"}

        is_buy = side.lower() == "buy"
        reference_price = self.get_reference_price(coin, desired_price)
        max_deviation = reference_price * Decimal("0.05")
        if is_buy:
            limit_price = min(desired_price, reference_price + (max_deviation * Decimal("0.5")))
        else:
            limit_price = max(desired_price, reference_price - (max_deviation * Decimal("0.5")))

        lower_bound = reference_price - max_deviation
        upper_bound = reference_price + max_deviation
        limit_price = max(lower_bound, min(upper_bound, limit_price))

        tick_size, precision = self.get_tick_size_and_precision(asset_id)
        rounded_ticks = (limit_price / tick_size).quantize(Decimal("1"))
        limit_price = rounded_ticks * tick_size
        quantizer = Decimal("1").scaleb(-precision)
        limit_price = limit_price.quantize(quantizer)

        size_str = str(size.normalize())
        order_wire = {
            "a": asset_id,
            "b": is_buy,
            "p": str(limit_price),
            "s": size_str,
            "r": False,
            "t": {"limit": {"tif": "Gtc"}}
        }
        action = {"type": "order", "orders": [order_wire], "grouping": "na"}
        nonce = int(time.time() * 1000)
        signature = self.sign_l1_action_exact(action, None, nonce, None, True)
        payload = {"action": action, "nonce": nonce, "signature": signature, "vaultAddress": None}

        result = self._post_exchange(payload)
        if result is None:
            return {"success": False, "mode": "live", "reason": "http_error", "notional": "0"}
        if result.get("status") != "ok":
            logger.error(f"Exchange rejected order for {coin}: {result}")
            return {"success": False, "mode": "live", "reason": "exchange_rejected", "notional": "0"}

        statuses = result.get("response", {}).get("data", {}).get("statuses", [])
        for status in statuses:
            if "error" in status:
                logger.error(f"Order status error for {coin}: {status}")
                return {"success": False, "mode": "live", "reason": "status_error", "notional": "0"}

        notional = abs(size * limit_price)
        logger.info(f"LIVE order success {coin} {side.upper()} size={size_str} limit={limit_price}")
        return {"success": True, "mode": "live", "filled_price": str(limit_price), "notional": str(notional)}

    def place_trigger_order(
        self,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
        reduce_only: bool = True,
        is_market: bool = True,
    ) -> Dict[str, Any]:
        """
        Place a trigger order (TP/SL) on Hyperliquid.
        tpsl must be "tp" or "sl".
        """
        if tpsl not in {"tp", "sl"}:
            return {"success": False, "reason": "invalid_tpsl"}

        if self.execution_mode != "live" or not self.enable_mainnet_trading:
            logger.info(f"PAPER trigger order {coin} {tpsl.upper()} {side.upper()} size={size} trigger={trigger_price}")
            return {"success": True, "mode": "paper", "order_id": None}

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for trigger order {coin}")
            return {"success": False, "reason": "asset_not_found"}

        is_buy = side.lower() == "buy"
        tick_size, precision = self.get_tick_size_and_precision(asset_id)

        rounded_ticks = (trigger_price / tick_size).quantize(Decimal("1"))
        trigger_price = rounded_ticks * tick_size
        quantizer = Decimal("1").scaleb(-precision)
        trigger_price = trigger_price.quantize(quantizer)

        order_wire = {
            "a": asset_id,
            "b": is_buy,
            "p": str(trigger_price),
            "s": str(size.normalize()),
            "r": bool(reduce_only),
            "t": {
                "trigger": {
                    "isMarket": bool(is_market),
                    "triggerPx": str(trigger_price),
                    "tpsl": tpsl
                }
            }
        }

        action = {"type": "order", "orders": [order_wire], "grouping": "positionTpsl"}
        nonce = int(time.time() * 1000)
        signature = self.sign_l1_action_exact(action, None, nonce, None, True)
        payload = {"action": action, "nonce": nonce, "signature": signature, "vaultAddress": None}

        result = self._post_exchange(payload)
        if result is None:
            return {"success": False, "reason": "http_error"}
        if result.get("status") != "ok":
            logger.error(f"Exchange rejected trigger order for {coin}: {result}")
            return {"success": False, "reason": "exchange_rejected"}

        statuses = result.get("response", {}).get("data", {}).get("statuses", [])
        for status in statuses:
            if "error" in status:
                logger.error(f"Trigger order status error for {coin}: {status}")
                return {"success": False, "reason": "status_error"}

        order_ids = self._extract_order_ids(result)
        order_id = order_ids[0] if order_ids else None

        logger.info(
            f"LIVE trigger order placed {coin} {tpsl.upper()} {side.upper()} "
            f"size={size} trigger={trigger_price} oid={order_id}"
        )
        return {"success": True, "order_id": order_id}

    def cancel_order(self, coin: str, order_id: int) -> bool:
        """Cancel a single order by oid."""
        if self.execution_mode != "live" or not self.enable_mainnet_trading:
            logger.info(f"PAPER cancel order {coin} oid={order_id}")
            return True

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for cancel {coin} oid={order_id}")
            return False

        action = {"type": "cancel", "cancels": [{"a": asset_id, "o": int(order_id)}]}
        nonce = int(time.time() * 1000)
        signature = self.sign_l1_action_exact(action, None, nonce, None, True)
        payload = {"action": action, "nonce": nonce, "signature": signature, "vaultAddress": None}

        result = self._post_exchange(payload)
        if result is None:
            return False
        if result.get("status") != "ok":
            logger.warning(f"Cancel rejected for {coin} oid={order_id}: {result}")
            return False

        logger.info(f"Cancel success {coin} oid={order_id}")
        return True

    def upsert_protective_orders(
        self,
        coin: str,
        position_size: Decimal,
        is_long: bool,
        stop_loss_price: Decimal,
        take_profit_price: Decimal,
        current_stop_order_id: Optional[int] = None,
        current_take_profit_order_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Replace on-exchange protective SL/TP orders for an open position.
        Cancels existing protective orders if provided, then places new SL and TP triggers.
        """
        if self.execution_mode != "live" or not self.enable_mainnet_trading:
            return {
                "success": True,
                "stop_loss_order_id": None,
                "take_profit_order_id": None,
            }

        close_side = "sell" if is_long else "buy"
        close_size = abs(position_size)

        if close_size <= 0:
            return {"success": False, "reason": "invalid_size"}

        if current_stop_order_id is not None:
            self.cancel_order(coin, current_stop_order_id)
        if current_take_profit_order_id is not None:
            self.cancel_order(coin, current_take_profit_order_id)

        sl_res = self.place_trigger_order(
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=stop_loss_price,
            tpsl="sl",
            reduce_only=True,
            is_market=True,
        )
        if not sl_res.get("success"):
            return {"success": False, "reason": f"stop_loss_place_failed:{sl_res.get('reason', 'unknown')}"}

        tp_res = self.place_trigger_order(
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=take_profit_price,
            tpsl="tp",
            reduce_only=True,
            is_market=True,
        )
        if not tp_res.get("success"):
            sl_oid = sl_res.get("order_id")
            if sl_oid is not None:
                self.cancel_order(coin, sl_oid)
            return {"success": False, "reason": f"take_profit_place_failed:{tp_res.get('reason', 'unknown')}"}

        return {
            "success": True,
            "stop_loss_order_id": sl_res.get("order_id"),
            "take_profit_order_id": tp_res.get("order_id"),
        }