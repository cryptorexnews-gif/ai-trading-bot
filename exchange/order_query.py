import time
from decimal import Decimal
from typing import Any, Dict, List, Optional


class OrderQueryService:
    """Order query/matching/reconciliation logic for open and protective orders."""

    def __init__(self, get_open_orders, cancel_order):
        self.get_open_orders = get_open_orders
        self.cancel_order = cancel_order

    @staticmethod
    def _normalize_side(side_value: Any) -> str:
        raw = str(side_value).strip().lower()
        if raw in {"b", "buy", "bid", "long", "true"}:
            return "buy"
        if raw in {"a", "s", "sell", "ask", "short", "false"}:
            return "sell"
        return ""

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
    def extract_order_oid(order: Dict[str, Any]) -> Optional[int]:
        if not isinstance(order, dict):
            return None

        direct = order.get("oid")
        if direct is not None:
            return int(direct)

        nested = order.get("order", {})
        if isinstance(nested, dict):
            nested_oid = nested.get("oid")
            if nested_oid is not None:
                return int(nested_oid)

        resting = order.get("resting", {})
        if isinstance(resting, dict):
            resting_oid = resting.get("oid")
            if resting_oid is not None:
                return int(resting_oid)

        return None

    def extract_order_side(self, order: Dict[str, Any]) -> str:
        if not isinstance(order, dict):
            return ""
        for candidate in [order.get("side"), order.get("dir"), order.get("b")]:
            side = self._normalize_side(candidate)
            if side:
                return side

        nested = order.get("order", {})
        if isinstance(nested, dict):
            for candidate in [nested.get("side"), nested.get("dir"), nested.get("b")]:
                side = self._normalize_side(candidate)
                if side:
                    return side

        return ""

    @staticmethod
    def extract_order_size(order: Dict[str, Any]) -> Decimal:
        if not isinstance(order, dict):
            return Decimal("0")
        candidates = [order.get("sz"), order.get("s"), order.get("size"), order.get("origSz")]
        nested = order.get("order", {})
        if isinstance(nested, dict):
            candidates.extend([nested.get("sz"), nested.get("s"), nested.get("size"), nested.get("origSz")])

        for c in candidates:
            try:
                val = Decimal(str(c))
            except Exception:
                val = Decimal("0")
            if val != 0:
                return val

        return Decimal("0")

    @staticmethod
    def extract_trigger_px(order: Dict[str, Any]) -> Decimal:
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

        nested = order.get("order", {})
        if isinstance(nested, dict):
            candidates.extend([nested.get("triggerPx"), nested.get("tpTriggerPx"), nested.get("slTriggerPx")])
            nested_trigger = nested.get("trigger", {})
            if isinstance(nested_trigger, dict):
                candidates.append(nested_trigger.get("triggerPx"))

        for c in candidates:
            try:
                px = Decimal(str(c))
            except Exception:
                px = Decimal("0")
            if px > 0:
                return px

        return Decimal("0")

    @staticmethod
    def extract_tpsl(order: Dict[str, Any]) -> str:
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

        nested = order.get("order", {})
        if isinstance(nested, dict):
            candidates.append(nested.get("tpsl"))
            candidates.append(nested.get("triggerType"))
            nested_trigger = nested.get("trigger", {})
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
    def extract_reduce_only(order: Dict[str, Any]) -> bool:
        if not isinstance(order, dict):
            return False

        candidates: List[Any] = [order.get("r"), order.get("reduceOnly"), order.get("isReduceOnly")]
        nested = order.get("order", {})
        if isinstance(nested, dict):
            candidates.extend([nested.get("r"), nested.get("reduceOnly"), nested.get("isReduceOnly")])

        for c in candidates:
            if isinstance(c, bool) and c:
                return True
            if str(c).strip().lower() in {"true", "1"}:
                return True

        return False

    def order_matches(
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

        order_side = self.extract_order_side(order)
        if order_side != side.lower():
            return False

        order_size = abs(self.extract_order_size(order))
        wanted_size = abs(size)
        if wanted_size <= 0:
            return False
        if not self._is_close_enough(order_size, wanted_size, rel_tol=size_rel_tol):
            return False

        order_trigger_px = self.extract_trigger_px(order)
        if order_trigger_px <= 0:
            return False
        if not self._is_close_enough(order_trigger_px, trigger_price, rel_tol=trigger_rel_tol):
            return False

        if enforce_reduce_only and not self.extract_reduce_only(order):
            return False

        if required_tpsl:
            order_tpsl = self.extract_tpsl(order)
            if order_tpsl and order_tpsl != required_tpsl.lower():
                return False
            if not order_tpsl:
                return False

        return True

    def find_order_by_characteristics(
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
            if not self.order_matches(
                order=order,
                coin=coin,
                side=side,
                size=size,
                trigger_price=trigger_price,
                required_tpsl=required_tpsl,
            ):
                continue

            oid = self.extract_order_oid(order)
            if oid is not None:
                candidates.append(int(oid))

        if not candidates:
            return None
        return max(candidates)

    def list_matching_trigger_orders(
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
            if not self.order_matches(
                order=order,
                coin=coin,
                side=side,
                size=size,
                trigger_price=trigger_price,
                required_tpsl=required_tpsl,
            ):
                continue

            oid = self.extract_order_oid(order)
            if oid is None:
                continue

            matches.append(
                {
                    "oid": int(oid),
                    "trigger_px": self.extract_trigger_px(order),
                    "size": abs(self.extract_order_size(order)),
                }
            )

        return matches

    @staticmethod
    def select_best_match_oid(matches: List[Dict[str, Any]], trigger_price: Decimal) -> Optional[int]:
        if not matches:
            return None
        best = min(matches, key=lambda m: abs(m["trigger_px"] - trigger_price))
        return int(best["oid"])

    def wait_for_trigger_order_id(
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
            strict_match = self.find_order_by_characteristics(
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

            relaxed_match = self.find_order_by_characteristics(
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

    def find_latest_protective_order_id(self, user: str, coin: str, side: str, tpsl: str) -> Optional[int]:
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

            order_side = self.extract_order_side(order)
            if order_side != side.lower():
                continue

            if not self.extract_reduce_only(order):
                continue

            order_tpsl = self.extract_tpsl(order)
            if order_tpsl and order_tpsl != tpsl.lower():
                continue

            oid = self.extract_order_oid(order)
            if oid is None:
                continue

            candidates.append(int(oid))

        if not candidates:
            return None
        return max(candidates)

    def cancel_duplicate_trigger_orders(
        self,
        user: str,
        coin: str,
        side: str,
        size: Decimal,
        trigger_price: Decimal,
        tpsl: str,
        keep_oid: int,
    ) -> None:
        strict_matches = self.list_matching_trigger_orders(
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

    def cancel_existing_coin_protective_orders(self, trading_user: str, coin: str, close_side: str) -> int:
        open_orders = self.get_open_orders(trading_user, force_refresh=True)
        to_cancel: List[int] = []

        for order in open_orders:
            if not isinstance(order, dict):
                continue

            order_coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
            if not order_coin and isinstance(order.get("order"), dict):
                order_coin = str(order["order"].get("coin", order["order"].get("symbol", ""))).strip().upper()
            if order_coin != coin.upper():
                continue

            order_side = self.extract_order_side(order)
            if order_side != close_side:
                continue

            trigger_px = self.extract_trigger_px(order)
            if trigger_px <= 0:
                continue

            if not self.extract_reduce_only(order):
                continue

            oid = self.extract_order_oid(order)
            if oid is None:
                continue

            to_cancel.append(oid)

        cancelled = 0
        for oid in sorted(set(to_cancel)):
            if self.cancel_order(coin, oid):
                cancelled += 1

        return cancelled