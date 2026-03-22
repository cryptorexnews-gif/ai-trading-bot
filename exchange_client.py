import logging
import os
import time
from decimal import Decimal, ROUND_DOWN
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
    build_update_leverage_action,
)
from exchange.parsers import (
    extract_order_ids,
    extract_statuses,
    get_first_status_error,
    has_acknowledged_order_status,
)
from exchange.signing import sign_l1_action_exact
from exchange.transport import post_exchange_with_circuit_breaker, post_json_with_circuit_breaker
from utils.circuit_breaker import get_or_create_circuit_breaker
from utils.decimals import safe_decimal
from utils.http import create_robust_session

logger = logging.getLogger(__name__)


class HyperliquidExchangeClient:
    """
    Hyperliquid client (live-only).
    Includes auth fallback between direct signer mode and master-wallet mode.
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

        self.vault_address = (vault_address or "").strip() or None
        self.master_wallet_address = (os.getenv("HYPERLIQUID_WALLET_ADDRESS", "") or "").strip() or None

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

        logger.info(
            f"Exchange client initialized: base_url={self.base_url}, mode={self.execution_mode}, "
            f"mainnet={self.enable_mainnet_trading}, signer={self.get_wallet_address_masked()} "
            f"(master={self._mask_address(self.master_wallet_address)}, vault={self._mask_address(self.vault_address)})"
        )

    def _live_orders_enabled(self) -> bool:
        return self.execution_mode == "live" and self.enable_mainnet_trading

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
    def _is_close_enough(
        a: Decimal,
        b: Decimal,
        rel_tol: Decimal = Decimal("0.02"),
        abs_tol: Decimal = Decimal("0.00000001"),
    ) -> bool:
        if a == b:
            return True
        diff = abs(a - b)
        scale = max(abs(a), abs(b), Decimal("1"))
        return diff <= max(abs_tol, scale * rel_tol)

    @staticmethod
    def _extract_order_oid(order: Dict[str, Any]) -> Optional[int]:
        if not isinstance(order, dict):
            return None
        direct_oid = order.get("oid")
        if direct_oid is not None:
            return int(direct_oid)

        nested_order = order.get("order", {})
        if isinstance(nested_order, dict):
            nested_oid = nested_order.get("oid")
            if nested_oid is not None:
                return int(nested_oid)

        resting = order.get("resting", {})
        if isinstance(resting, dict):
            resting_oid = resting.get("oid")
            if resting_oid is not None:
                return int(resting_oid)
        return None

    @staticmethod
    def _extract_order_side(order: Dict[str, Any]) -> str:
        if not isinstance(order, dict):
            return ""
        for candidate in [order.get("side"), order.get("dir"), order.get("b")]:
            side = HyperliquidExchangeClient._normalize_side(candidate)
            if side:
                return side

        nested_order = order.get("order", {})
        if isinstance(nested_order, dict):
            for candidate in [nested_order.get("side"), nested_order.get("dir"), nested_order.get("b")]:
                side = HyperliquidExchangeClient._normalize_side(candidate)
                if side:
                    return side
        return ""

    @staticmethod
    def _extract_order_size(order: Dict[str, Any]) -> Decimal:
        if not isinstance(order, dict):
            return Decimal("0")
        candidates = [order.get("sz"), order.get("s"), order.get("size"), order.get("origSz")]
        nested_order = order.get("order", {})
        if isinstance(nested_order, dict):
            candidates.extend(
                [nested_order.get("sz"), nested_order.get("s"), nested_order.get("size"), nested_order.get("origSz")]
            )
        for c in candidates:
            val = safe_decimal(c, Decimal("0"))
            if val != 0:
                return val
        return Decimal("0")

    @staticmethod
    def _extract_trigger_px(order: Dict[str, Any]) -> Decimal:
        if not isinstance(order, dict):
            return Decimal("0")
        candidates = [order.get("triggerPx"), order.get("tpTriggerPx"), order.get("slTriggerPx")]
        trigger_obj = order.get("trigger", {})
        if isinstance(trigger_obj, dict):
            candidates.append(trigger_obj.get("triggerPx"))
        order_type = order.get("orderType", {})
        if isinstance(order_type, dict):
            trigger_obj_2 = order_type.get("trigger", {})
            if isinstance(trigger_obj_2, dict):
                candidates.append(trigger_obj_2.get("triggerPx"))

        nested_order = order.get("order", {})
        if isinstance(nested_order, dict):
            candidates.extend([nested_order.get("triggerPx"), nested_order.get("tpTriggerPx"), nested_order.get("slTriggerPx")])
            nested_trigger = nested_order.get("trigger", {})
            if isinstance(nested_trigger, dict):
                candidates.append(nested_trigger.get("triggerPx"))
            nested_order_type = nested_order.get("orderType", {})
            if isinstance(nested_order_type, dict):
                nested_trigger_2 = nested_order_type.get("trigger", {})
                if isinstance(nested_trigger_2, dict):
                    candidates.append(nested_trigger_2.get("triggerPx"))

        for c in candidates:
            px = safe_decimal(c, Decimal("0"))
            if px > 0:
                return px
        return Decimal("0")

    @staticmethod
    def _extract_tpsl(order: Dict[str, Any]) -> str:
        if not isinstance(order, dict):
            return ""

        candidates: List[Any] = [order.get("tpsl"), order.get("triggerType")]
        trigger_obj = order.get("trigger", {})
        if isinstance(trigger_obj, dict):
            candidates.append(trigger_obj.get("tpsl"))
            candidates.append(trigger_obj.get("triggerType"))

        order_type = order.get("orderType", {})
        if isinstance(order_type, dict):
            trigger_obj_2 = order_type.get("trigger", {})
            if isinstance(trigger_obj_2, dict):
                candidates.append(trigger_obj_2.get("tpsl"))
                candidates.append(trigger_obj_2.get("triggerType"))

        nested_order = order.get("order", {})
        if isinstance(nested_order, dict):
            candidates.append(nested_order.get("tpsl"))
            candidates.append(nested_order.get("triggerType"))
            nested_trigger = nested_order.get("trigger", {})
            if isinstance(nested_trigger, dict):
                candidates.append(nested_trigger.get("tpsl"))
                candidates.append(nested_trigger.get("triggerType"))

        for c in candidates:
            value = str(c or "").strip().lower()
            if value in {"tp", "sl"}:
                return value
        if bool(order.get("isTp")):
            return "tp"
        if bool(order.get("isSl")):
            return "sl"
        return ""

    @staticmethod
    def _extract_reduce_only(order: Dict[str, Any]) -> bool:
        if not isinstance(order, dict):
            return False
        candidates: List[Any] = [order.get("r"), order.get("reduceOnly"), order.get("isReduceOnly")]
        nested_order = order.get("order", {})
        if isinstance(nested_order, dict):
            candidates.extend([nested_order.get("r"), nested_order.get("reduceOnly"), nested_order.get("isReduceOnly")])

        for c in candidates:
            if isinstance(c, bool) and c:
                return True
            if str(c).strip().lower() in {"true", "1"}:
                return True
        return False

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
        if not isinstance(order, dict):
            return False

        order_coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
        if not order_coin and isinstance(order.get("order"), dict):
            order_coin = str(order["order"].get("coin", order["order"].get("symbol", ""))).strip().upper()
        if order_coin != coin.upper():
            return False

        order_side = self._extract_order_side(order)
        if order_side != side.lower():
            return False

        order_size = abs(self._extract_order_size(order))
        wanted_size = abs(size)
        if wanted_size <= 0:
            return False
        if not self._is_close_enough(order_size, wanted_size, rel_tol=size_rel_tol):
            return False

        order_trigger_px = self._extract_trigger_px(order)
        if order_trigger_px <= 0:
            return False
        if not self._is_close_enough(order_trigger_px, trigger_price, rel_tol=trigger_rel_tol):
            return False

        if enforce_reduce_only and not self._extract_reduce_only(order):
            return False

        if required_tpsl:
            order_tpsl = self._extract_tpsl(order)
            if order_tpsl and order_tpsl != required_tpsl.lower():
                return False
            if not order_tpsl:
                return False

        return True

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
        open_orders = self.get_open_orders(user, force_refresh=force_refresh)
        candidates: List[int] = []

        for order in open_orders:
            if not self._order_matches(
                order=order,
                coin=coin,
                side=side,
                size=size,
                trigger_price=trigger_price,
                required_tpsl=required_tpsl,
            ):
                continue

            oid = self._extract_order_oid(order)
            if oid is not None:
                candidates.append(int(oid))

        if not candidates:
            return None
        return max(candidates)

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

    def get_batch_info(self, requests_payload: List[Dict[str, Any]], timeout: Optional[int] = None) -> List[Any]:
        """
        Batch /info helper.
        Returns an empty list on failure to keep call sites simple and safe.
        """
        if not requests_payload:
            return []
        result = self._post_info({"type": "batch", "requests": requests_payload}, timeout=timeout)
        return result if isinstance(result, list) else []

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

    def _is_valid_eth_address(self, value: Optional[str]) -> bool:
        if not value:
            return False
        raw = str(value).strip()
        return raw.startswith("0x") and len(raw) == 42

    def _get_effective_vault_address(self) -> Optional[str]:
        """
        Returns vault address only if it is configured and structurally valid.
        """
        if self._is_valid_eth_address(self.vault_address):
            return self.vault_address
        return None

    def _post_signed_action_once(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
        vault_address_override: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        nonce = self._next_nonce()
        vault_for_sign = vault_address_override
        signature = sign_l1_action_exact(
            account=self.account,
            action=action,
            vault_address=vault_for_sign,
            nonce=nonce,
            expires_after=None,
            is_mainnet=True,
        )
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": vault_for_sign,
        }
        return self._post_exchange(payload, timeout=timeout)

    def _post_signed_action_with_master_retry(self, action: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
        now = time.time()
        if now < self._auth_block_until:
            logger.error(
                f"Auth cooldown active ({int(self._auth_block_until - now)}s left), skipping signed action."
            )
            return {"status": "err", "response": "auth_cooldown_active"}

        signer = (self.account.address or "").lower()
        master = (self.master_wallet_address or "").lower()
        effective_vault = self._get_effective_vault_address()

        attempts: List[Optional[str]] = []

        if effective_vault:
            attempts.append(effective_vault)
        else:
            attempts.append(None)

        if master and master != signer and master not in [str(a).lower() for a in attempts if a is not None]:
            attempts.append(master)

        if None not in attempts:
            attempts.append(None)

        result: Optional[Dict[str, Any]] = None
        for idx, vault_mode in enumerate(attempts, start=1):
            if idx > 1:
                time.sleep(0.2)

            result = self._post_signed_action_once(action, timeout=timeout, vault_address_override=vault_mode)
            if not self._is_auth_error(result):
                self._auth_error_count = 0
                return result

            logger.warning(
                f"Auth mode attempt {idx}/{len(attempts)} failed "
                f"(vault={self._mask_address(vault_mode)}): {result}"
            )

        self._auth_error_count += 1
        if self._auth_error_count >= 2:
            self._auth_block_until = time.time() + self._auth_cooldown_sec
            logger.error(
                f"Persistent auth errors. Enabling auth cooldown for {int(self._auth_cooldown_sec)}s"
            )

        return result

    def _list_matching_trigger_orders(
        self,
        user: str,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
        strict_tpsl: bool = True,
    ) -> List[Dict[str, Any]]:
        open_orders = self.get_open_orders(user, force_refresh=True)
        matches: List[Dict[str, Any]] = []

        for order in open_orders:
            required_tpsl = tpsl if strict_tpsl else None
            if not self._order_matches(
                order=order,
                coin=coin,
                side=side,
                size=size,
                trigger_price=trigger_price,
                required_tpsl=required_tpsl,
            ):
                continue

            oid = self._extract_order_oid(order)
            if oid is None:
                continue

            matches.append(
                {
                    "oid": int(oid),
                    "trigger_px": self._extract_trigger_px(order),
                    "size": abs(self._extract_order_size(order)),
                }
            )

        return matches

    def _select_best_match_oid(self, matches: List[Dict[str, Any]], trigger_price: Decimal) -> Optional[int]:
        if not matches:
            return None
        best = min(matches, key=lambda m: abs(m["trigger_px"] - trigger_price))
        return int(best["oid"])

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
        matches = self._list_matching_trigger_orders(
            user=user,
            coin=coin,
            side=side,
            size=size,
            trigger_price=trigger_price,
            tpsl=tpsl,
            strict_tpsl=strict_tpsl,
        )
        return self._select_best_match_oid(matches, trigger_price)

    def _find_latest_protective_order_id(
        self,
        user: str,
        coin: str,
        side: str,
        tpsl: str,
    ) -> Optional[int]:
        open_orders = self.get_open_orders(user, force_refresh=True)
        candidates: List[int] = []

        for order in open_orders:
            if not isinstance(order, dict):
                continue

            order_coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
            if not order_coin and isinstance(order.get("order"), dict):
                order_coin = str(order["order"].get("coin", order["order"].get("symbol", ""))).strip().upper()
            if order_coin != coin.upper():
                continue

            order_side = self._extract_order_side(order)
            if order_side != side.lower():
                continue

            if not self._extract_reduce_only(order):
                continue

            order_tpsl = self._extract_tpsl(order)
            if order_tpsl and order_tpsl != tpsl.lower():
                continue

            oid = self._extract_order_oid(order)
            if oid is None:
                continue

            candidates.append(int(oid))

        if not candidates:
            return None
        return max(candidates)

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
        for _ in range(attempts):
            strict_match = self._find_order_by_characteristics(
                user=user,
                coin=coin,
                side=side,
                size=size,
                trigger_price=trigger_price,
                required_tpsl=tpsl,
                force_refresh=True,
            )
            if strict_match is not None:
                return strict_match

            relaxed_match = self._find_order_by_characteristics(
                user=user,
                coin=coin,
                side=side,
                size=size,
                trigger_price=trigger_price,
                required_tpsl=None,
                force_refresh=True,
            )
            if relaxed_match is not None:
                return relaxed_match

            time.sleep(delay_sec)

        return None

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
        strict_matches = self._list_matching_trigger_orders(
            user=user,
            coin=coin,
            side=side,
            size=size,
            trigger_price=trigger_price,
            tpsl=tpsl,
            strict_tpsl=True,
        )
        for match in strict_matches:
            oid = int(match["oid"])
            if oid == keep_oid:
                continue
            self.cancel_order(coin, oid)
            logger.warning(f"Cancelled duplicate {tpsl.upper()} order for {coin}, oid={oid}, keep_oid={keep_oid}")

    def _cancel_existing_coin_protective_orders(self, coin: str, close_side: str) -> int:
        open_orders = self.get_open_orders(self.account.address, force_refresh=True)
        to_cancel: List[int] = []

        for order in open_orders:
            if not isinstance(order, dict):
                continue

            order_coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
            if not order_coin and isinstance(order.get("order"), dict):
                order_coin = str(order["order"].get("coin", order["order"].get("symbol", ""))).strip().upper()
            if order_coin != coin.upper():
                continue

            order_side = self._extract_order_side(order)
            if order_side != close_side:
                continue

            trigger_px = self._extract_trigger_px(order)
            if trigger_px <= 0:
                continue

            if not self._extract_reduce_only(order):
                continue

            oid = self._extract_order_oid(order)
            if oid is None:
                continue

            to_cancel.append(oid)

        cancelled = 0
        for oid in sorted(set(to_cancel)):
            if self.cancel_order(coin, oid):
                cancelled += 1

        if cancelled > 0:
            logger.warning(
                f"Cancelled {cancelled} stale protective trigger orders for {coin} side={close_side.upper()}"
            )

        return cancelled

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

    def get_open_orders(self, user: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        now = time.time()
        cached = self._open_orders_cache_by_user.get(user)
        if not force_refresh and cached and (now - float(cached.get("at", 0.0))) < self._open_orders_cache_ttl_sec:
            data = cached.get("data", [])
            return data if isinstance(data, list) else []

        data = self._post_info({"type": "openOrders", "user": user})
        orders = data if isinstance(data, list) else []
        self._open_orders_cache_by_user[user] = {"at": now, "data": orders}
        return orders

    def are_order_ids_open(self, user: str, coin: str, order_ids: List[int]) -> bool:
        wanted = {int(oid) for oid in order_ids if oid is not None}
        if not wanted:
            return False

        open_orders = self.get_open_orders(user, force_refresh=True)
        found = set()

        for order in open_orders:
            if not isinstance(order, dict):
                continue

            order_coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
            if not order_coin and isinstance(order.get("order"), dict):
                order_coin = str(order["order"].get("coin", order["order"].get("symbol", ""))).strip().upper()
            if order_coin != coin.upper():
                continue

            oid = self._extract_order_oid(order)
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
            user=self.account.address,
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
            user=self.account.address,
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
            user=self.account.address,
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
            self._cancel_duplicate_trigger_orders(
                user=self.account.address,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=stop_loss_price,
                tpsl="sl",
                keep_oid=existing_sl_id,
            )
            self._cancel_duplicate_trigger_orders(
                user=self.account.address,
                coin=coin,
                side=close_side,
                size=close_size,
                trigger_price=take_profit_price,
                tpsl="tp",
                keep_oid=existing_tp_id,
            )
            return {
                "success": True,
                "stop_loss_order_id": existing_sl_id,
                "take_profit_order_id": existing_tp_id,
            }

        self._cancel_existing_coin_protective_orders(coin, close_side)

        if current_stop_order_id is not None:
            self.cancel_order(coin, current_stop_order_id)
        if current_take_profit_order_id is not None:
            self.cancel_order(coin, current_take_profit_order_id)

        is_close_buy = close_side == "buy"
        orders = [
            {
                "coin": coin,
                "is_buy": is_close_buy,
                "sz": close_size,
                "limit_px": stop_loss_price,
                "order_type": {
                    "trigger": {
                        "isMarket": True,
                        "triggerPx": stop_loss_price,
                        "tpsl": "sl",
                    }
                },
                "reduce_only": True,
            },
            {
                "coin": coin,
                "is_buy": is_close_buy,
                "sz": close_size,
                "limit_px": take_profit_price,
                "order_type": {
                    "trigger": {
                        "isMarket": True,
                        "triggerPx": take_profit_price,
                        "tpsl": "tp",
                    }
                },
                "reduce_only": True,
            },
        ]

        bulk_res = self.bulk_orders(orders, grouping="normalTpsl")
        if not bulk_res.get("success"):
            return {"success": False, "reason": f"bulk_tpsl_failed:{bulk_res.get('reason', 'unknown')}"}

        sl_id = self._wait_for_trigger_order_id(
            user=self.account.address,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=stop_loss_price,
            tpsl="sl",
            attempts=8,
            delay_sec=0.5,
        )
        tp_id = self._wait_for_trigger_order_id(
            user=self.account.address,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=take_profit_price,
            tpsl="tp",
            attempts=8,
            delay_sec=0.5,
        )

        if sl_id is None:
            sl_id = self._find_latest_protective_order_id(
                user=self.account.address,
                coin=coin,
                side=close_side,
                tpsl="sl",
            )
        if tp_id is None:
            tp_id = self._find_latest_protective_order_id(
                user=self.account.address,
                coin=coin,
                side=close_side,
                tpsl="tp",
            )

        if sl_id is None or tp_id is None:
            return {"success": False, "reason": "missing_trigger_order_id_after_bulk"}

        self._cancel_duplicate_trigger_orders(
            user=self.account.address,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=stop_loss_price,
            tpsl="sl",
            keep_oid=sl_id,
        )
        self._cancel_duplicate_trigger_orders(
            user=self.account.address,
            coin=coin,
            side=close_side,
            size=close_size,
            trigger_price=take_profit_price,
            tpsl="tp",
            keep_oid=tp_id,
        )

        return {
            "success": True,
            "stop_loss_order_id": sl_id,
            "take_profit_order_id": tp_id,
        }