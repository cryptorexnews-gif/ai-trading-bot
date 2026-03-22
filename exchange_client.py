import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from eth_account import Account

from exchange.market_rules import (
    default_tick_size_for_asset,
    infer_tick_size_and_precision_from_mid,
    normalize_size_for_decimals,
)
from exchange.order_builder import (
    build_cancel_action,
    build_limit_order_action,
    build_trigger_order_action,
    build_update_leverage_action,
)
from exchange.parsers import (
    extract_order_ids,
    extract_statuses,
    get_first_status_error,
    has_acknowledged_order_status,
    is_master_wallet_not_found_error,
)
from exchange.signing import sign_l1_action_exact
from exchange.transport import post_exchange_with_circuit_breaker, post_json_with_circuit_breaker
from utils.circuit_breaker import get_or_create_circuit_breaker
from utils.decimals import safe_decimal
from utils.http import create_robust_session

logger = logging.getLogger(__name__)


class HyperliquidExchangeClient:
    """
    Hyperliquid client (live-only, master wallet mode):
    - HTTP + circuit breaker
    - EIP-712 signing
    - order payload builder separato
    - parser separati
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

        self._last_nonce: int = 0
        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_at = 0.0
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at = 0.0
        self._mids_cache_ttl = 30.0

        self._info_cb = get_or_create_circuit_breaker("hyperliquid_info", failure_threshold=5, recovery_timeout=30.0)
        self._exchange_cb = get_or_create_circuit_breaker("hyperliquid_exchange", failure_threshold=3, recovery_timeout=60.0)

        logger.info(
            f"Exchange client initialized: base_url={self.base_url}, mode={self.execution_mode}, "
            f"mainnet={self.enable_mainnet_trading}, signer={self.get_wallet_address_masked()} (master-only)"
        )

    def __repr__(self) -> str:
        return (
            f"<HyperliquidExchangeClient base_url={self.base_url} "
            f"mode={self.execution_mode} signer={self.get_wallet_address_masked()} master_only=True>"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def _live_orders_enabled(self) -> bool:
        return self.execution_mode == "live" and self.enable_mainnet_trading

    @staticmethod
    def _is_ok_result(result: Optional[Dict[str, Any]]) -> bool:
        return isinstance(result, dict) and result.get("status") == "ok"

    @staticmethod
    def _mask_address(address: Optional[str]) -> str:
        if not address or len(address) < 12:
            return "none"
        return f"{address[:6]}...{address[-4:]}"

    @staticmethod
    def _normalize_side(side_value: Any) -> str:
        raw = str(side_value).strip().lower()
        if raw in {"b", "buy", "bid", "long", "true"}:
            return "buy"
        if raw in {"a", "s", "sell", "ask", "short", "false"}:
            return "sell"
        return ""

    @staticmethod
    def _extract_trigger_px(order: Dict[str, Any]) -> Decimal:
        if not isinstance(order, dict):
            return Decimal("0")

        direct = order.get("triggerPx")
        if direct is not None:
            return safe_decimal(direct, Decimal("0"))

        trigger_obj = order.get("trigger", {})
        if isinstance(trigger_obj, dict):
            nested = trigger_obj.get("triggerPx")
            if nested is not None:
                return safe_decimal(nested, Decimal("0"))

        order_type = order.get("orderType", {})
        if isinstance(order_type, dict):
            trigger_obj_2 = order_type.get("trigger", {})
            if isinstance(trigger_obj_2, dict):
                nested2 = trigger_obj_2.get("triggerPx")
                if nested2 is not None:
                    return safe_decimal(nested2, Decimal("0"))

        return Decimal("0")

    @staticmethod
    def _extract_tpsl(order: Dict[str, Any]) -> str:
        if not isinstance(order, dict):
            return ""

        direct = str(order.get("tpsl", "")).strip().lower()
        if direct in {"tp", "sl"}:
            return direct

        trigger_obj = order.get("trigger", {})
        if isinstance(trigger_obj, dict):
            nested = str(trigger_obj.get("tpsl", "")).strip().lower()
            if nested in {"tp", "sl"}:
                return nested

        order_type = order.get("orderType", {})
        if isinstance(order_type, dict):
            trigger_obj_2 = order_type.get("trigger", {})
            if isinstance(trigger_obj_2, dict):
                nested2 = str(trigger_obj_2.get("tpsl", "")).strip().lower()
                if nested2 in {"tp", "sl"}:
                    return nested2

        return ""

    @staticmethod
    def _is_close_enough(a: Decimal, b: Decimal, rel_tol: Decimal = Decimal("0.02"), abs_tol: Decimal = Decimal("0.00000001")) -> bool:
        if a == b:
            return True
        diff = abs(a - b)
        scale = max(abs(a), abs(b), Decimal("1"))
        return diff <= max(abs_tol, scale * rel_tol)

    def _next_nonce(self) -> int:
        current_ms = int(time.time() * 1000)
        if current_ms <= self._last_nonce:
            current_ms = self._last_nonce + 1
        self._last_nonce = current_ms
        return current_ms

    def _post_info(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        timeout = timeout or self.info_timeout
        return post_json_with_circuit_breaker(
            session=self.session,
            url=f"{self.base_url}/info",
            payload=payload,
            timeout=timeout,
            circuit_breaker=self._info_cb,
            endpoint_label=f"/info type={payload.get('type', 'unknown')}",
        )

    def _post_exchange(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        timeout = timeout or self.exchange_timeout
        return post_exchange_with_circuit_breaker(
            session=self.session,
            url=f"{self.base_url}/exchange",
            payload=payload,
            timeout=timeout,
            circuit_breaker=self._exchange_cb,
            endpoint_label="/exchange",
        )

    def _post_signed_action_once(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        nonce = self._next_nonce()
        signature = sign_l1_action_exact(
            account=self.account,
            action=action,
            nonce=nonce,
            expires_after=None,
            is_mainnet=True,
        )
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None,
        }
        return self._post_exchange(payload, timeout=timeout)

    def _post_signed_action_with_master_retry(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        result = self._post_signed_action_once(action, timeout=timeout)

        max_wallet_error_retries = 3
        attempt = 0
        while is_master_wallet_not_found_error(result) and attempt < max_wallet_error_retries:
            attempt += 1
            backoff_sec = 0.25 * attempt
            logger.warning(
                f"Exchange reported master wallet not found (attempt {attempt}/{max_wallet_error_retries}). "
                f"Retrying with fresh nonce in {backoff_sec:.2f}s."
            )
            time.sleep(backoff_sec)
            result = self._post_signed_action_once(action, timeout=timeout)

        if is_master_wallet_not_found_error(result):
            logger.error(
                "Persistent master wallet auth error after retries. "
                f"Signer={self.get_wallet_address_masked()}"
            )

        return result

    def _round_price_to_tick(self, asset_id: int, price: Decimal) -> Decimal:
        tick_size, precision = self.get_tick_size_and_precision(asset_id)
        rounded_ticks = (price / tick_size).quantize(Decimal("1"))
        rounded_price = rounded_ticks * tick_size
        quantizer = Decimal("1").scaleb(-precision)
        return rounded_price.quantize(quantizer)

    def _resolve_limit_price(self, coin: str, side: str, desired_price: Decimal, asset_id: int) -> Decimal:
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

        return self._round_price_to_tick(asset_id, limit_price)

    def _normalize_size_for_coin(self, coin: str, size: Decimal) -> Decimal:
        sz_decimals = self.get_sz_decimals(coin)
        if sz_decimals is None:
            return size if size > 0 else Decimal("0")
        return normalize_size_for_decimals(size, sz_decimals)

    def _find_trigger_order_id(
        self,
        user: str,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
        strict_tpsl: bool = True,
    ) -> Optional[int]:
        open_orders = self.get_open_orders(user)
        wanted_coin = coin.upper()
        wanted_side = side.lower()
        wanted_tpsl = tpsl.lower()
        wanted_size = abs(size)

        best_oid: Optional[int] = None
        best_score: Optional[Decimal] = None

        for order in open_orders:
            if not isinstance(order, dict):
                continue

            order_coin = str(order.get("coin", "")).strip().upper()
            if order_coin != wanted_coin:
                continue

            order_side = self._normalize_side(order.get("side"))
            if not order_side:
                order_side = self._normalize_side(order.get("dir"))
            if order_side != wanted_side:
                continue

            order_size = abs(safe_decimal(order.get("sz", order.get("s", "0")), Decimal("0")))
            if not self._is_close_enough(order_size, wanted_size, rel_tol=Decimal("0.05")):
                continue

            order_trigger_px = self._extract_trigger_px(order)
            if order_trigger_px <= 0:
                continue
            if not self._is_close_enough(order_trigger_px, trigger_price, rel_tol=Decimal("0.015")):
                continue

            order_tpsl = self._extract_tpsl(order)
            if strict_tpsl and order_tpsl and order_tpsl != wanted_tpsl:
                continue
            if strict_tpsl and not order_tpsl:
                continue

            oid_raw = order.get("oid")
            if oid_raw is None:
                continue

            try:
                oid = int(oid_raw)
            except (TypeError, ValueError):
                continue

            score = abs(order_trigger_px - trigger_price)
            if best_score is None or score < best_score:
                best_score = score
                best_oid = oid

        return best_oid

    def _wait_for_trigger_order_id(
        self,
        user: str,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
        attempts: int = 6,
        delay_sec: float = 0.5,
    ) -> Optional[int]:
        for _ in range(attempts):
            strict_match = self._find_trigger_order_id(
                user=user,
                coin=coin,
                side=side,
                size=size,
                trigger_price=trigger_price,
                tpsl=tpsl,
                strict_tpsl=True,
            )
            if strict_match is not None:
                return strict_match

            relaxed_match = self._find_trigger_order_id(
                user=user,
                coin=coin,
                side=side,
                size=size,
                trigger_price=trigger_price,
                tpsl=tpsl,
                strict_tpsl=False,
            )
            if relaxed_match is not None:
                return relaxed_match

            time.sleep(delay_sec)

        return None

    def get_derived_address(self) -> str:
        return self.account.address

    def get_wallet_address_masked(self) -> str:
        return self._mask_address(self.account.address)

    @staticmethod
    def validate_wallet_address(private_key: str, expected_address: str) -> bool:
        derived = Account.from_key(private_key).address
        return derived.lower() == expected_address.lower()

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

    def get_open_orders(self, user: str) -> List[Dict[str, Any]]:
        data = self._post_info({"type": "openOrders", "user": user})
        return data if isinstance(data, list) else []

    def are_order_ids_open(self, user: str, coin: str, order_ids: List[int]) -> bool:
        wanted = {int(oid) for oid in order_ids if oid is not None}
        if not wanted:
            return False

        open_orders = self.get_open_orders(user)
        found = set()

        for order in open_orders:
            if not isinstance(order, dict):
                continue
            order_coin = str(order.get("coin", "")).strip().upper()
            if order_coin != coin.upper():
                continue
            oid = order.get("oid")
            if oid is None:
                continue
            try:
                found.add(int(oid))
            except (TypeError, ValueError):
                continue

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

        is_buy = side.lower() == "buy"
        limit_price = self._resolve_limit_price(coin=coin, side=side, desired_price=desired_price, asset_id=asset_id)

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

        notional = abs(normalized_size * limit_price)
        logger.info(f"LIVE order success {coin} {side.upper()} size={normalized_size} limit={limit_price} reduce_only={reduce_only}")
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
        if not self._live_orders_enabled():
            return {"success": False, "reason": "live_disabled_fail_closed"}

        if tpsl not in {"tp", "sl"}:
            return {"success": False, "reason": "invalid_tpsl"}

        normalized_size = self._normalize_size_for_coin(coin, abs(size))
        if normalized_size <= 0:
            return {"success": False, "reason": "invalid_size_after_normalization"}

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for trigger order {coin}")
            return {"success": False, "reason": "asset_not_found"}

        is_buy = side.lower() == "buy"
        rounded_trigger = self._round_price_to_tick(asset_id, trigger_price)

        action = build_trigger_order_action(
            asset_id=asset_id,
            is_buy=is_buy,
            trigger_price=rounded_trigger,
            size=normalized_size,
            tpsl=tpsl,
            reduce_only=reduce_only,
            is_market=is_market,
        )

        result = self._post_signed_action_with_master_retry(action)
        if result is None:
            return {"success": False, "reason": "http_error"}
        if not self._is_ok_result(result):
            logger.error(f"Exchange rejected trigger order for {coin}: {result}")
            return {"success": False, "reason": "exchange_rejected"}

        statuses = extract_statuses(result)
        status_error = get_first_status_error(statuses)
        if status_error is not None:
            logger.error(f"Trigger order status error for {coin}: {status_error}")
            return {"success": False, "reason": "status_error"}

        if statuses and not has_acknowledged_order_status(statuses):
            logger.error(f"Trigger order not acknowledged by Hyperliquid statuses for {coin}: {statuses}")
            return {"success": False, "reason": "not_acknowledged"}

        order_ids = extract_order_ids(result)
        order_id = order_ids[0] if order_ids else None

        if order_id is None:
            order_id = self._wait_for_trigger_order_id(
                user=self.account.address,
                coin=coin,
                side=side,
                size=normalized_size,
                trigger_price=rounded_trigger,
                tpsl=tpsl,
                attempts=6,
                delay_sec=0.5,
            )

        logger.info(
            f"LIVE trigger order placed {coin} {tpsl.upper()} {side.upper()} "
            f"size={normalized_size} trigger={rounded_trigger} oid={order_id}"
        )
        return {"success": True, "order_id": order_id}

    def cancel_order(self, coin: str, order_id: int) -> bool:
        if not self._live_orders_enabled():
            logger.error("Live cancel blocked: EXECUTION_MODE must be live and ENABLE_MAINNET_TRADING=true")
            return False

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"Asset ID not found for cancel {coin} oid={order_id}")
            return False

        action = build_cancel_action(asset_id=asset_id, order_id=order_id)
        result = self._post_signed_action_with_master_retry(action)
        if result is None:
            return False
        if not self._is_ok_result(result):
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
        if not self._live_orders_enabled():
            return {"success": False, "reason": "live_disabled_fail_closed"}

        close_side = "sell" if is_long else "buy"
        close_size = abs(position_size)
        if close_size <= 0:
            return {"success": False, "reason": "invalid_size"}

        existing_sl_id = current_stop_order_id
        existing_tp_id = current_take_profit_order_id

        if existing_sl_id is None:
            existing_sl_id = self._wait_for_trigger_order_id(
                user=self.account.address,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=stop_loss_price,
                tpsl="sl",
                attempts=3,
                delay_sec=0.3,
            )

        if existing_tp_id is None:
            existing_tp_id = self._wait_for_trigger_order_id(
                user=self.account.address,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=take_profit_price,
                tpsl="tp",
                attempts=3,
                delay_sec=0.3,
            )

        if existing_sl_id is not None and existing_tp_id is not None:
            return {
                "success": True,
                "stop_loss_order_id": existing_sl_id,
                "take_profit_order_id": existing_tp_id,
            }

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

        sl_id = sl_res.get("order_id")
        tp_id = tp_res.get("order_id")

        if sl_id is None:
            sl_id = self._wait_for_trigger_order_id(
                user=self.account.address,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=stop_loss_price,
                tpsl="sl",
                attempts=6,
                delay_sec=0.5,
            )
        if tp_id is None:
            tp_id = self._wait_for_trigger_order_id(
                user=self.account.address,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=take_profit_price,
                tpsl="tp",
                attempts=6,
                delay_sec=0.5,
            )

        if sl_id is None or tp_id is None:
            return {"success": False, "reason": "missing_trigger_order_id"}

        return {
            "success": True,
            "stop_loss_order_id": sl_id,
            "take_profit_order_id": tp_id,
        }