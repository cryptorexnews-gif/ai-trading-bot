import logging
import os
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

from eth_account import Account

from exchange.api_client import ExchangeAPIClient
from exchange.market_rules import (
    default_tick_size_for_asset,
    infer_tick_size_and_precision_from_mid,
    normalize_size_for_decimals,
)
from exchange.order_builder import (
    build_cancel_action,
    build_limit_order_action,
    build_update_leverage_action,
)
from exchange.order_query import OrderQueryService
from exchange.parsers import (
    extract_order_ids,
    extract_statuses,
    get_first_status_error,
    has_acknowledged_order_status,
)
from exchange.protective_orders import ProtectiveOrdersService
from exchange.signing import sign_l1_action_exact
from utils.circuit_breaker import get_or_create_circuit_breaker
from utils.decimals import safe_decimal
from utils.http import create_robust_session

logger = logging.getLogger(__name__)


class HyperliquidExchangeClient:
    """
    Hyperliquid client (live-only).
    Coerenza operativa:
    - Usa UNA sola identità utente trading da .env (HYPERLIQUID_WALLET_ADDRESS).
    - Nessun utente alternativo, nessun fallback signer/vault.
    - Firma sempre senza vaultAddress.
    """

    def __init__(
        self,
        base_url: str,
        private_key: str,
        enable_mainnet_trading: bool = False,
        execution_mode: str = "live",
        meta_cache_ttl_sec: int = 120,
        paper_slippage_bps: Decimal = Decimal("5"),
        info_timeout: int = 15,
        exchange_timeout: int = 30,
        vault_address: Optional[str] = None,
    ):
        self.base_url = base_url
        self.enable_mainnet_trading = enable_mainnet_trading
        self.execution_mode = "live" if execution_mode != "live" else execution_mode
        self.meta_cache_ttl_sec = meta_cache_ttl_sec
        self.paper_slippage_bps = paper_slippage_bps
        self.info_timeout = info_timeout
        self.exchange_timeout = exchange_timeout

        self.session = create_robust_session()
        self.account = Account.from_key(private_key)

        env_wallet = (os.getenv("HYPERLIQUID_WALLET_ADDRESS", "") or "").strip()
        if not self._is_valid_wallet_address_format(env_wallet):
            raise ValueError(
                "HYPERLIQUID_WALLET_ADDRESS invalido o mancante. "
                "È richiesto un address 0x... lungo 42 caratteri da .env."
            )

        if self.account.address.lower() != env_wallet.lower():
            raise ValueError(
                "HYPERLIQUID_PRIVATE_KEY non corrisponde a HYPERLIQUID_WALLET_ADDRESS."
            )

        if vault_address:
            logger.warning("vault_address fornito ma ignorato: runtime forzato senza vault fallback.")

        self._trading_user_address = env_wallet
        self._fixed_vault_for_signing = None

        self._last_nonce: int = 0
        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_at = 0.0
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at = 0.0
        self._mids_cache_ttl = 30.0

        self._open_orders_cache_by_user: Dict[str, Dict[str, Any]] = {}
        self._open_orders_cache_ttl_sec = 2.0

        self._auth_error_count = 0
        self._auth_block_until = 0.0
        self._auth_cooldown_sec = 120.0

        self._info_cb = get_or_create_circuit_breaker(
            "hyperliquid_info", failure_threshold=5, recovery_timeout=30.0
        )
        self._exchange_cb = get_or_create_circuit_breaker(
            "hyperliquid_exchange", failure_threshold=3, recovery_timeout=60.0
        )

        self._api_client = ExchangeAPIClient(
            session=self.session,
            base_url=self.base_url,
            info_timeout=self.info_timeout,
            exchange_timeout=self.exchange_timeout,
            info_cb=self._info_cb,
            exchange_cb=self._exchange_cb,
            meta_cache_ttl_sec=self.meta_cache_ttl_sec,
        )
        self._order_query = OrderQueryService(
            get_open_orders=self.get_open_orders,
            cancel_order=self.cancel_order,
        )
        self._protective_orders = ProtectiveOrdersService(
            client=self,
            order_query_service=self._order_query,
        )

        logger.info(
            f"Exchange client initialized: base_url={self.base_url}, mode={self.execution_mode}, "
            f"mainnet={self.enable_mainnet_trading}, signer={self.get_wallet_address_masked()} "
            f"(trading_user={self._mask_address(self._trading_user_address)}, signing_vault=none)"
        )

    def _live_orders_enabled(self) -> bool:
        return self.execution_mode == "live" and self.enable_mainnet_trading

    @staticmethod
    def _mask_address(address: Optional[str]) -> str:
        if not address or len(address) < 12:
            return "none"
        return f"{address[:6]}...{address[-4:]}"

    @staticmethod
    def _is_valid_wallet_address_format(value: str) -> bool:
        raw = str(value or "").strip()
        return raw.startswith("0x") and len(raw) == 42

    @staticmethod
    def _is_ok_result(result: Optional[Dict[str, Any]]) -> bool:
        return isinstance(result, dict) and result.get("status") == "ok"

    @staticmethod
    def _is_auth_error(result: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(result, dict):
            return False
        if result.get("status") != "err":
            return False
        msg = str(result.get("response", "")).lower()
        return (
            "wallet" in msg and "does not exist" in msg
        ) or ("api wallet" in msg and "does not exist" in msg)

    @staticmethod
    def validate_wallet_address(private_key: str, expected_address: str) -> bool:
        derived = Account.from_key(private_key).address
        return derived.lower() == expected_address.lower()

    def _next_nonce(self) -> int:
        current_ms = int(time.time() * 1000)
        if current_ms <= self._last_nonce:
            current_ms = self._last_nonce + 1
        self._last_nonce = current_ms
        return current_ms

    def _post_info(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        return self._api_client.post_info(payload, timeout=timeout)

    def get_batch_info(self, requests_payload: List[Dict[str, Any]], timeout: Optional[int] = None) -> List[Any]:
        return self._api_client.get_batch_info(requests_payload=requests_payload, timeout=timeout)

    def _post_exchange(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        return self._api_client.post_exchange(payload=payload, timeout=timeout)

    def _post_signed_action_once(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
        vault_address_override: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        nonce = self._next_nonce()
        signature = sign_l1_action_exact(
            account=self.account,
            action=action,
            vault_address=vault_address_override,
            nonce=nonce,
            expires_after=None,
            is_mainnet=True,
        )
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": vault_address_override,
        }
        return self._post_exchange(payload, timeout=timeout)

    def _post_signed_action_with_master_retry(self, action: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Nome mantenuto per compatibilità interna.
        Comportamento attuale: identità fissa da .env, nessun retry con utente/vault alternativi.
        """
        now = time.time()
        if now < self._auth_block_until:
            logger.error(
                f"Auth cooldown active ({int(self._auth_block_until - now)}s left), skipping signed action."
            )
            return {"status": "err", "response": "auth_cooldown_active"}

        result = self._post_signed_action_once(
            action=action,
            timeout=timeout,
            vault_address_override=self._fixed_vault_for_signing,
        )

        if self._is_auth_error(result):
            self._auth_error_count += 1
            logger.warning(
                f"Auth failed with fixed trading identity "
                f"(trading_user={self._mask_address(self._trading_user_address)}, signer={self.get_wallet_address_masked()}): {result}"
            )
            if self._auth_error_count >= 2:
                self._auth_block_until = time.time() + self._auth_cooldown_sec
                logger.error(
                    f"Persistent auth errors. Enabling auth cooldown for {int(self._auth_cooldown_sec)}s"
                )
        else:
            self._auth_error_count = 0

        return result

    def get_wallet_address_masked(self) -> str:
        return self._mask_address(self.account.address)

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

    def get_open_orders(self, user: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        requested_user = str(user or "").strip()
        effective_user = requested_user if requested_user else self._trading_user_address

        now = time.time()
        cached = self._open_orders_cache_by_user.get(effective_user)
        if not force_refresh and cached and (now - float(cached.get("at", 0.0))) < self._open_orders_cache_ttl_sec:
            data = cached.get("data", [])
            return data if isinstance(data, list) else []

        data = self._post_info({"type": "openOrders", "user": effective_user})
        orders = data if isinstance(data, list) else []
        self._open_orders_cache_by_user[effective_user] = {"at": now, "data": orders}
        return orders

    def are_order_ids_open(self, user: str, coin: str, order_ids: List[int]) -> bool:
        wanted = {int(oid) for oid in order_ids if oid is not None}
        if not wanted:
            return False

        effective_user = self._trading_user_address
        open_orders = self.get_open_orders(effective_user, force_refresh=True)
        found = set()

        for order in open_orders:
            if not isinstance(order, dict):
                continue

            order_coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
            if not order_coin and isinstance(order.get("order"), dict):
                order_coin = str(order["order"].get("coin", order["order"].get("symbol", ""))).strip().upper()
            if order_coin != coin.upper():
                continue

            oid = self._order_query.extract_order_oid(order)
            if oid is None:
                continue
            found.add(oid)

        return wanted.issubset(found)

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
            return Decimal("0.01"), 2

        universe = meta.get("universe", [])
        if not (0 <= asset_id < len(universe)):
            return Decimal("0.01"), 2

        coin = universe[asset_id].get("name", "")
        mids = self.get_all_mids()
        if mids is not None and coin in mids:
            return infer_tick_size_and_precision_from_mid(str(mids.get(coin, "0")))
        return default_tick_size_for_asset(asset_id)

    def _normalize_size_for_coin(self, coin: str, size: Decimal) -> Decimal:
        if size <= 0:
            return Decimal("0")
        sz_decimals = self.get_sz_decimals(coin)
        normalized = normalize_size_for_decimals(size, sz_decimals if sz_decimals is not None else -1)
        if normalized <= 0:
            return Decimal("0")
        return normalized

    def _round_price_to_tick(self, asset_id: int, price: Decimal) -> Decimal:
        if price <= 0:
            return price
        tick_size, precision = self.get_tick_size_and_precision(asset_id)
        if tick_size <= 0:
            return price

        units = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
        rounded = units * tick_size

        if precision >= 0:
            quantizer = Decimal("1").scaleb(-precision)
            rounded = rounded.quantize(quantizer)

        return rounded

    def _resolve_limit_price(self, coin: str, side: str, desired_price: Decimal, asset_id: int) -> Decimal:
        reference_price = self.get_reference_price(coin, desired_price)
        if reference_price <= 0:
            reference_price = desired_price

        if reference_price <= 0:
            return self._round_price_to_tick(asset_id, Decimal("0"))

        execution_buffer = Decimal("0.0025")
        if side.lower() == "buy":
            aggressive = reference_price * (Decimal("1") + execution_buffer)
            target = max(desired_price, aggressive) if desired_price > 0 else aggressive
        else:
            aggressive = reference_price * (Decimal("1") - execution_buffer)
            target = min(desired_price, aggressive) if desired_price > 0 else aggressive

        return self._round_price_to_tick(asset_id, target)

    # Compatibility wrappers for tests/internal legacy calls
    def _order_matches(
        self,
        order: Dict[str, Any],
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        required_tpsl: Optional[str] = None,
        enforce_reduce_only: bool = True,
        size_rel_tol: Decimal = Decimal("0.10"),
        trigger_rel_tol: Decimal = Decimal("0.03"),
    ) -> bool:
        return self._order_query.order_matches(
            order=order,
            coin=coin,
            side=side,
            size=size,
            trigger_price=trigger_price,
            required_tpsl=required_tpsl,
            enforce_reduce_only=enforce_reduce_only,
            size_rel_tol=size_rel_tol,
            trigger_rel_tol=trigger_rel_tol,
        )

    def _find_order_by_characteristics(
        self,
        user: str,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        required_tpsl: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[int]:
        return self._order_query.find_order_by_characteristics(
            user=user,
            coin=coin,
            side=side,
            size=size,
            trigger_price=trigger_price,
            required_tpsl=required_tpsl,
            force_refresh=force_refresh,
        )

    def _wait_for_trigger_order_id(
        self,
        user: str,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
        attempts: int = 10,
        delay_sec: float = 0.6,
    ) -> Optional[int]:
        return self._order_query.wait_for_trigger_order_id(
            user=user,
            coin=coin,
            side=side,
            size=size,
            trigger_price=trigger_price,
            tpsl=tpsl,
            attempts=attempts,
            delay_sec=delay_sec,
        )

    def _find_latest_protective_order_id(
        self,
        user: str,
        coin: str,
        side: str,
        tpsl: str,
    ) -> Optional[int]:
        return self._order_query.find_latest_protective_order_id(user=user, coin=coin, side=side, tpsl=tpsl)

    def _cancel_duplicate_trigger_orders(
        self,
        user: str,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
        keep_oid: int,
    ) -> None:
        self._order_query.cancel_duplicate_trigger_orders(
            user=user,
            coin=coin,
            side=side,
            size=size,
            trigger_price=trigger_price,
            tpsl=tpsl,
            keep_oid=keep_oid,
        )

    def _cancel_existing_coin_protective_orders(self, coin: str, close_side: str) -> int:
        return self._order_query.cancel_existing_coin_protective_orders(
            trading_user=self._trading_user_address,
            coin=coin,
            close_side=close_side,
        )

    def set_leverage(self, coin: str, leverage: int) -> bool:
        if not self._live_orders_enabled():
            logger.error("Live leverage blocked: EXECUTION_MODE must be live and ENABLE_MAINNET_TRADING=true")
            return False

        leverage = max(1, leverage)
        max_leverage = self.get_max_leverage(coin)
        if leverage > max_leverage:
            leverage = max_leverage

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for {coin}")
            return False

        action = build_update_leverage_action(asset_id=asset_id, leverage=leverage)
        result = self._post_signed_action_with_master_retry(action)
        if result is None:
            return False
        if self._is_ok_result(result):
            logger.info(f"LIVE leverage set {coin} -> {leverage}x")
            return True
        logger.error(f"Set leverage failed for {coin}: {result}")
        return False

    def place_order(self, coin: str, side: str, size: Decimal, desired_price: Decimal, reduce_only: bool = False) -> Dict[str, Any]:
        if not self._live_orders_enabled():
            return {"success": False, "mode": "live", "reason": "live_disabled_fail_closed", "notional": "0"}

        normalized_size = self._normalize_size_for_coin(coin, abs(size))
        if normalized_size <= 0:
            return {"success": False, "mode": "live", "reason": "invalid_size_after_normalization", "notional": "0"}

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for {coin}")
            return {"success": False, "mode": "live", "reason": "asset_not_found", "notional": "0"}

        normalized_side = side.lower()
        if normalized_side not in {"buy", "sell"}:
            return {"success": False, "mode": "live", "reason": "invalid_side", "notional": "0"}

        is_buy = normalized_side == "buy"
        limit_price = self._resolve_limit_price(coin=coin, side=normalized_side, desired_price=desired_price, asset_id=asset_id)
        if limit_price <= 0:
            return {"success": False, "mode": "live", "reason": "invalid_limit_price", "notional": "0"}

        action = build_limit_order_action(
            asset_id=asset_id,
            is_buy=is_buy,
            price=limit_price,
            size=normalized_size,
            reduce_only=reduce_only,
        )

        result = self._post_signed_action_with_master_retry(action)
        if result is None:
            return {"success": False, "mode": "live", "reason": "http_error", "notional": "0"}
        if not self._is_ok_result(result):
            logger.error(f"Exchange rejected order for {coin}: {result}")
            return {"success": False, "mode": "live", "reason": "exchange_rejected", "notional": "0"}

        statuses = extract_statuses(result)
        status_error = get_first_status_error(statuses)
        if status_error is not None:
            logger.error(f"Order status error for {coin}: {status_error}")
            return {"success": False, "mode": "live", "reason": "status_error", "notional": "0"}

        if statuses and not has_acknowledged_order_status(statuses):
            logger.error(f"Order not acknowledged by Hyperliquid statuses for {coin}: {statuses}")
            return {"success": False, "mode": "live", "reason": "not_acknowledged", "notional": "0"}

        order_ids = extract_order_ids(result)
        notional = abs(normalized_size * limit_price)
        logger.info(
            f"LIVE order success {coin} {normalized_side.upper()} size={normalized_size} "
            f"limit={limit_price} reduce_only={reduce_only} oids={order_ids}"
        )
        return {
            "success": True,
            "mode": "live",
            "filled_price": str(limit_price),
            "executed_size": str(normalized_size),
            "notional": str(notional),
        }

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
        if not self._live_orders_enabled():
            return {"success": False, "reason": "live_disabled_fail_closed"}

        if tpsl not in {"tp", "sl"}:
            return {"success": False, "reason": "invalid_tpsl"}

        normalized_side = side.lower()
        if normalized_side not in {"buy", "sell"}:
            return {"success": False, "reason": "invalid_side"}

        normalized_size = self._normalize_size_for_coin(coin, abs(size))
        if normalized_size <= 0:
            return {"success": False, "reason": "invalid_size_after_normalization"}

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for trigger order {coin}")
            return {"success": False, "reason": "asset_not_found"}

        rounded_trigger = self._round_price_to_tick(asset_id, trigger_price)
        if rounded_trigger <= 0:
            return {"success": False, "reason": "invalid_trigger_price"}

        existing_oid = self._wait_for_trigger_order_id(
            user=self._trading_user_address,
            coin=coin,
            side=normalized_side,
            size=normalized_size,
            trigger_price=rounded_trigger,
            tpsl=tpsl,
            attempts=1,
            delay_sec=0.0,
        )
        if existing_oid is not None:
            return {"success": True, "order_id": existing_oid}

        order_wire = {
            "a": asset_id,
            "b": normalized_side == "buy",
            "p": str(rounded_trigger),
            "s": str(normalized_size.normalize()),
            "r": bool(reduce_only),
            "t": {"trigger": {"isMarket": bool(is_market), "triggerPx": str(rounded_trigger), "tpsl": tpsl}},
        }
        action = {"type": "order", "orders": [order_wire], "grouping": "normalTpsl"}

        result = self._post_signed_action_with_master_retry(action)
        if result is None:
            return {"success": False, "reason": "http_error"}
        if not self._is_ok_result(result):
            logger.error(f"Exchange rejected trigger order for {coin}: {result}")
            return {"success": False, "reason": "exchange_rejected"}

        statuses = extract_statuses(result)
        status_error = get_first_status_error(statuses)
        if status_error is not None:
            return {"success": False, "reason": "status_error"}

        if statuses and not has_acknowledged_order_status(statuses):
            return {"success": False, "reason": "not_acknowledged"}

        immediate_oids = extract_order_ids(result)
        if immediate_oids:
            return {"success": True, "order_id": int(immediate_oids[0])}

        order_id = self._wait_for_trigger_order_id(
            user=self._trading_user_address,
            coin=coin,
            side=normalized_side,
            size=normalized_size,
            trigger_price=rounded_trigger,
            tpsl=tpsl,
            attempts=16,
            delay_sec=0.75,
        )

        if order_id is not None:
            return {"success": True, "order_id": order_id}

        fallback_oid = self._find_latest_protective_order_id(
            user=self._trading_user_address,
            coin=coin,
            side=normalized_side,
            tpsl=tpsl,
        )
        if fallback_oid is not None:
            logger.warning(
                f"Trigger order accepted and mapped via fallback for {coin} {tpsl.upper()} "
                f"{normalized_side.upper()} oid={fallback_oid}"
            )
            return {"success": True, "order_id": fallback_oid}

        return {"success": False, "reason": "missing_trigger_order_id"}

    def bulk_orders(self, orders: List[Dict[str, Any]], grouping: str = "na") -> Dict[str, Any]:
        if not self._live_orders_enabled():
            return {"success": False, "reason": "live_disabled_fail_closed"}

        if not isinstance(orders, list) or len(orders) == 0:
            return {"success": False, "reason": "empty_orders"}

        wire_orders: List[Dict[str, Any]] = []

        for order in orders:
            coin = str(order.get("coin", "")).strip().upper()
            if not coin:
                return {"success": False, "reason": "missing_coin"}

            asset_id = self.get_asset_id(coin)
            if asset_id is None:
                return {"success": False, "reason": f"asset_not_found:{coin}"}

            is_buy = bool(order.get("is_buy", False))
            side = "buy" if is_buy else "sell"

            raw_size = safe_decimal(order.get("sz", "0"), Decimal("0"))
            normalized_size = self._normalize_size_for_coin(coin, abs(raw_size))
            if normalized_size <= 0:
                return {"success": False, "reason": f"invalid_size:{coin}"}

            raw_px = safe_decimal(order.get("limit_px", "0"), Decimal("0"))
            if raw_px <= 0:
                return {"success": False, "reason": f"invalid_limit_px:{coin}"}

            order_type = order.get("order_type", {"limit": {"tif": "Gtc"}})
            if not isinstance(order_type, dict):
                return {"success": False, "reason": f"invalid_order_type:{coin}"}

            if "trigger" in order_type:
                trigger_obj = order_type.get("trigger", {})
                trigger_px = safe_decimal(trigger_obj.get("triggerPx", "0"), Decimal("0"))
                if trigger_px <= 0:
                    return {"success": False, "reason": f"invalid_trigger_px:{coin}"}
                rounded_trigger = self._round_price_to_tick(asset_id, trigger_px)
                order_type = {
                    "trigger": {
                        "isMarket": bool(trigger_obj.get("isMarket", True)),
                        "triggerPx": str(rounded_trigger),
                        "tpsl": str(trigger_obj.get("tpsl", "")).strip().lower(),
                    }
                }
                rounded_px = self._round_price_to_tick(asset_id, raw_px)
            else:
                rounded_px = self._resolve_limit_price(
                    coin=coin,
                    side=side,
                    desired_price=raw_px,
                    asset_id=asset_id,
                )

            reduce_only = bool(order.get("reduce_only", False))

            wire_orders.append(
                {
                    "a": asset_id,
                    "b": is_buy,
                    "p": str(rounded_px),
                    "s": str(normalized_size.normalize()),
                    "r": reduce_only,
                    "t": order_type,
                }
            )

        action = {"type": "order", "orders": wire_orders, "grouping": grouping}
        result = self._post_signed_action_with_master_retry(action)

        if result is None:
            return {"success": False, "reason": "http_error"}
        if not self._is_ok_result(result):
            return {"success": False, "reason": "exchange_rejected", "raw": result}

        statuses = extract_statuses(result)
        status_error = get_first_status_error(statuses)
        if status_error is not None:
            return {"success": False, "reason": "status_error", "raw": result}

        if statuses and not has_acknowledged_order_status(statuses):
            return {"success": False, "reason": "not_acknowledged", "raw": result}

        return {"success": True, "order_ids": extract_order_ids(result), "raw": result}

    def cancel_order(self, coin: str, order_id: int) -> bool:
        if not self._live_orders_enabled():
            return False

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            return False

        action = build_cancel_action(asset_id=asset_id, order_id=order_id)
        result = self._post_signed_action_with_master_retry(action)
        if result is None:
            return False
        if not self._is_ok_result(result):
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
        return self._protective_orders.upsert_protective_orders(
            coin=coin,
            position_size=position_size,
            is_long=is_long,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            current_stop_order_id=current_stop_order_id,
            current_take_profit_order_id=current_take_profit_order_id,
        )

    def get_trading_user_address(self) -> str:
        return self._trading_user_address