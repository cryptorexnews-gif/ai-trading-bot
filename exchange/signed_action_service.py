import logging
import time
from typing import Any, Dict, Optional

from exchange.signing import sign_l1_action_exact, sign_l1_action_exact_legacy

logger = logging.getLogger(__name__)


class SignedActionService:
    """Handles signed Hyperliquid action posting with auth cooldown protection."""

    def __init__(self, account, post_exchange_func, is_auth_error_func):
        self.account = account
        self._post_exchange = post_exchange_func
        self._is_auth_error = is_auth_error_func

        self._last_nonce: int = 0
        self._auth_error_count = 0
        self._auth_block_until = 0.0
        self._auth_cooldown_sec = 120.0

    def next_nonce(self) -> int:
        current_ms = int(time.time() * 1000)
        if current_ms <= self._last_nonce:
            current_ms = self._last_nonce + 1
        self._last_nonce = current_ms
        return current_ms

    def _build_signature(
        self,
        action: Dict[str, Any],
        nonce: int,
        signature_mode: str = "padded",
    ) -> Dict[str, Any]:
        if signature_mode == "legacy":
            return sign_l1_action_exact_legacy(
                account=self.account,
                action=action,
                nonce=nonce,
                expires_after=None,
                is_mainnet=True,
            )
        return sign_l1_action_exact(
            account=self.account,
            action=action,
            nonce=nonce,
            expires_after=None,
            is_mainnet=True,
        )

    @staticmethod
    def _with_recovery_v(signature: Dict[str, Any]) -> Dict[str, Any]:
        s = dict(signature)
        raw_v = int(s.get("v", 27))
        if raw_v >= 27:
            s["v"] = raw_v - 27
        return s

    def _post_with_signature_strategy(
        self,
        action: Dict[str, Any],
        timeout: Optional[int],
        signature_mode: str,
        use_recovery_v: bool,
    ) -> Optional[Dict[str, Any]]:
        nonce = self.next_nonce()
        signature = self._build_signature(
            action=action,
            nonce=nonce,
            signature_mode=signature_mode,
        )

        if use_recovery_v:
            signature = self._with_recovery_v(signature)

        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
        }

        return self._post_exchange(payload, timeout)

    def post_signed_action_once(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
        signature_mode: str = "padded",
    ) -> Optional[Dict[str, Any]]:
        return self._post_with_signature_strategy(
            action=action,
            timeout=timeout,
            signature_mode=signature_mode,
            use_recovery_v=False,
        )

    def post_signed_action_with_auth_guard(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        if now < self._auth_block_until:
            return {"status": "err", "response": "auth_cooldown_active"}

        attempts = [
            ("padded", False),
            ("legacy", False),
            ("padded", True),
            ("legacy", True),
        ]

        result: Optional[Dict[str, Any]] = None
        for idx, (mode, recovery_v) in enumerate(attempts, start=1):
            if idx > 1:
                logger.warning(
                    f"Signed action auth-style rejection: retrying with signature mode={mode}, "
                    f"recovery_v={recovery_v}"
                )

            result = self._post_with_signature_strategy(
                action=action,
                timeout=timeout,
                signature_mode=mode,
                use_recovery_v=recovery_v,
            )

            if result is not None and not self._is_auth_error(result):
                self._auth_error_count = 0
                return result

        if self._is_auth_error(result):
            self._auth_error_count += 1
            if self._auth_error_count >= 2:
                self._auth_block_until = time.time() + self._auth_cooldown_sec
        else:
            self._auth_error_count = 0

        return result