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
        vault_address_override: Optional[str],
        nonce: int,
        signature_mode: str = "padded",
    ) -> Dict[str, Any]:
        if signature_mode == "legacy":
            return sign_l1_action_exact_legacy(
                account=self.account,
                action=action,
                vault_address=vault_address_override,
                nonce=nonce,
                expires_after=None,
                is_mainnet=True,
            )
        return sign_l1_action_exact(
            account=self.account,
            action=action,
            vault_address=vault_address_override,
            nonce=nonce,
            expires_after=None,
            is_mainnet=True,
        )

    def post_signed_action_once(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
        vault_address_override: Optional[str] = None,
        signature_mode: str = "padded",
    ) -> Optional[Dict[str, Any]]:
        nonce = self.next_nonce()
        signature = self._build_signature(
            action=action,
            vault_address_override=vault_address_override,
            nonce=nonce,
            signature_mode=signature_mode,
        )
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": vault_address_override,
        }
        return self._post_exchange(payload, timeout)

    def post_signed_action_with_auth_guard(
        self,
        action: Dict[str, Any],
        timeout: Optional[int] = None,
        vault_address_override: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        if now < self._auth_block_until:
            return {"status": "err", "response": "auth_cooldown_active"}

        result = self.post_signed_action_once(
            action=action,
            timeout=timeout,
            vault_address_override=vault_address_override,
            signature_mode="padded",
        )

        if self._is_auth_error(result):
            logger.warning("Signed action auth-style rejection: retrying once with legacy signature format")
            legacy_result = self.post_signed_action_once(
                action=action,
                timeout=timeout,
                vault_address_override=vault_address_override,
                signature_mode="legacy",
            )
            if legacy_result is not None and not self._is_auth_error(legacy_result):
                self._auth_error_count = 0
                return legacy_result
            result = legacy_result if legacy_result is not None else result

        if self._is_auth_error(result):
            self._auth_error_count += 1
            if self._auth_error_count >= 2:
                self._auth_block_until = time.time() + self._auth_cooldown_sec
        else:
            self._auth_error_count = 0

        return result