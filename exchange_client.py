import logging
import os
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

from eth_account import Account

from exchange.api_client import ExchangeAPIClient
from exchange.market_data_service import ExchangeMarketDataService
from exchange.market_rules import normalize_size_for_decimals
from exchange.order_execution_service import OrderExecutionService
from exchange.order_query import OrderQueryService
from exchange.protective_orders import ProtectiveOrdersService
from exchange.signed_action_service import SignedActionService
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
        self._market_data = ExchangeMarketDataService(self._api_client)

        self._signed_actions = SignedActionService(
            account=self.account,
            post_exchange_func=self._post_exchange,
            is_auth_error_func=self._is_auth_error,
        )

        self._order_query = OrderQueryService(
            get_open_orders=self.get_open_orders,
            cancel_order=self.cancel_order,
        )
        self._protective_orders = ProtectiveOrdersService(
            client=self,
            order_query_service=self._order_query,
        )
        self._execution = OrderExecutionService(self)

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

    def get_wallet_address_masked(self) -> str:
        return self._mask_address(self.account.address)

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
        return self._signed_actions.post_signed_action_once(
            action=action,
            timeout=timeout,
            vault_address_override=vault_address_override,
        )

    def _post_signed_action_with_master_retry(self, action: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Nome mantenuto per compatibilità interna.
        Comportamento attuale: identità fissa da .env, nessun retry con utente/vault alternativi.
        """
        return self._signed_actions.post_signed_action_with_auth_guard(
            action=action,
            timeout=timeout,
            vault_address_override=self._fixed_vault_for_signing,
        )

    def get_meta(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        return self._market_data.get_meta(force_refresh=force_refresh, fetcher=self._post_info)

    def get_all_mids(self, force_refresh: bool = False) -> Optional[Dict[str, str]]:
        return self._market_data.get_all_mids(force_refresh=force_refresh, fetcher=self._post_info)

    def get_user_state(self, user: str) -> Optional[Dict[str, Any]]:
        return self._market_data.get_user_state(user=user, fetcher=self._post_info)

    def get_open_orders(self, user: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        requested_user = str(user or "").strip()
        effective_user = requested_user if requested_user else self._trading_user_address
        return self._market_data.get_open_orders(
            user=effective_user,
            force_refresh=force_refresh,
            fetcher=self._post_info,
        )

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
        return self._market_data.get_asset_id(coin=coin, meta=self.get_meta(force_refresh=False))

    def get_max_leverage(self, coin: str) -> int:
        return self._market_data.get_max_leverage(coin=coin, meta=self.get_meta(force_refresh=False))

    def get_sz_decimals(self, coin: str) -> Optional[int]:
        return self._market_data.get_sz_decimals(coin=coin, meta=self.get_meta(force_refresh=False))

    def get_reference_price(self, coin: str, fallback_price: Decimal) -> Decimal:
        return self._market_data.get_reference_price(
            coin=coin,
            fallback_price=fallback_price,
            mids=self.get_all_mids(force_refresh=False),
        )

    def get_tick_size_and_precision(self, asset_id: int) -> Tuple[Decimal, int]:
        return self._market_data.get_tick_size_and_precision(
            asset_id=asset_id,
            meta=self.get_meta(force_refresh=False),
            mids=self.get_all_mids(force_refresh=False),
        )

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
        return self._execution.set_leverage(coin=coin, leverage=leverage)

    def place_order(self, coin: str, side: str, size: Decimal, desired_price: Decimal, reduce_only: bool = False) -> Dict[str, Any]:
        return self._execution.place_order(
            coin=coin,
            side=side,
            size=size,
            desired_price=desired_price,
            reduce_only=reduce_only,
        )

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
        return self._execution.place_trigger_order(
            coin=coin,
            side=side,
            size=size,
            trigger_price=trigger_price,
            tpsl=tpsl,
            reduce_only=reduce_only,
            is_market=is_market,
        )

    def bulk_orders(self, orders: List[Dict[str, Any]], grouping: str = "na") -> Dict[str, Any]:
        return self._execution.bulk_orders(orders=orders, grouping=grouping)

    def cancel_order(self, coin: str, order_id: int) -> bool:
        return self._execution.cancel_order(coin=coin, order_id=order_id)

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