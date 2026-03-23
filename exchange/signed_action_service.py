import logging
import time
from typing import Any, Dict, Optional

from exchange.signing import sign_l1_action_exact

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

    def _build_signature(self, action: Dict[str, Any], nonce: int) -> Dict[str, Any]:
        # Firma canonica unica (no legacy/recovery fallback)
        return sign_l1_action_exact(
            account=self.account,
            action=action,
            nonce=nonce,
            expires_after=None,
            is_mainnet=True,
        )

    def _post_once(self, action: Dict[str, Any], timeout: Optional[int]) -> Optional[Dict[str, Any]]:
        nonce = self.next_nonce()
        signature = self._build_signature(action=action, nonce=nonce)
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
    ) -> Optional[Dict[str, Any]]:
        return self._post_once(action=action, timeout=timeout)

    def post_signed_action_with_auth_guard(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        if now < self._auth_block_until:
            return {"status": "err", "response": "auth_cooldown_active"}

        # Due tentativi canonical-only (nuovo nonce al secondo tentativo)
        result = self._post_once(action=action, timeout=timeout)
        if result is not None and not self._is_auth_error(result):
            self._auth_error_count = 0
            return result

        logger.warning("Signed action auth-style rejection on canonical signature, retrying once with fresh nonce")
        result_retry = self._post_once(action=action, timeout=timeout)
        if result_retry is not None and not self._is_auth_error(result_retry):
            self._auth_error_count = 0
            return result_retry

        # Gestione cooldown auth
        final_result = result_retry if result_retry is not None else result
        if self._is_auth_error(final_result):
            self._auth_error_count += 1
            if self._auth_error_count >= 2:
                self._auth_block_until = time.time() + self._auth_cooldown_sec
                logger.error(
                    f"Auth error persisted on canonical signature; entering cooldown for "
                    f"{int(self._auth_cooldown_sec)}s"
                )
        else:
            self._auth_error_count = 0

        return final_result