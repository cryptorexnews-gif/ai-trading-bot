#!/usr/bin/env python3
"""
ORDINE MINIMALE PER HYPERLIQUID
Script che piazza UN ordine minimo con firma EIP-712 corretta.
Usa configurazione da .env file.
"""

import time
import requests
import os
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_typed_data
import msgpack
from Crypto.Hash import keccak

load_dotenv()

PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
ENABLE_MAINNET_TRADING = os.getenv("ENABLE_MAINNET_TRADING", "false").lower() == "true"
AUTO_CONFIRM_MINIMAL_ORDER = os.getenv("AUTO_CONFIRM_MINIMAL_ORDER", "false").lower() == "true"
BASE_URL = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
INFO_TIMEOUT = int(os.getenv("HYPERLIQUID_INFO_TIMEOUT", "15"))
EXCHANGE_TIMEOUT = int(os.getenv("HYPERLIQUID_EXCHANGE_TIMEOUT", "30"))


def mask_wallet(wallet: str) -> str:
    if not wallet or len(wallet) < 12:
        return "invalid_wallet"
    return f"{wallet[:6]}...{wallet[-4:]}"


def address_to_bytes(address):
    return bytes.fromhex(address[2:].lower())


def action_hash(action, vault_address, nonce, expires_after):
    data = msgpack.packb(action)
    data += nonce.to_bytes(8, "big")
    if vault_address is None:
        data += b"\x00"
    else:
        data += b"\x01"
        data += address_to_bytes(vault_address)
    if expires_after is not None:
        data += b"\x00"
        data += expires_after.to_bytes(8, "big")
    return keccak.new(data=data, digest_bits=256).digest()


def construct_phantom_agent(hash_bytes, is_mainnet=True):
    return {
        "source": "a" if is_mainnet else "b",
        "connectionId": "0x" + hash_bytes.hex()
    }


def l1_payload(phantom_agent):
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


def sign_l1_action_exact(wallet, action, vault_address, nonce, expires_after, is_mainnet=True):
    hash_bytes = action_hash(action, vault_address, nonce, expires_after)
    phantom_agent = construct_phantom_agent(hash_bytes, is_mainnet)
    data = l1_payload(phantom_agent)
    structured_data = encode_typed_data(full_message=data)
    signed = wallet.sign_message(structured_data)
    return {"r": hex(signed.r), "s": hex(signed.s), "v": signed.v}


def get_timestamp_ms():
    return int(time.time() * 1000)


def get_asset_id(coin):
    response = requests.post(f"{BASE_URL}/info", json={"type": "meta"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        meta = response.json()
        for i, asset in enumerate(meta.get("universe", [])):
            if asset.get("name") == coin:
                return i
    print(f"❌ Errore nel recupero ID asset per {coin}: status={response.status_code}")
    return None


def get_mid_price(coin):
    """Ottieni prezzo mid corrente da Hyperliquid."""
    response = requests.post(f"{BASE_URL}/info", json={"type": "allMids"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        mids = response.json()
        if coin in mids:
            return float(mids[coin])
    return None


def create_minimal_order(coin, is_buy, sz, limit_px):
    asset_id = get_asset_id(coin)
    if asset_id is None:
        print(f"❌ ID asset non trovato per {coin}")
        return None

    print(f"✅ ID asset per {coin}: {asset_id}")

    order_wire = {
        "a": asset_id,
        "b": is_buy,
        "p": str(limit_px),
        "s": str(sz),
        "r": False,
        "t": {"limit": {"tif": "Gtc"}}
    }

    return {
        "type": "order",
        "orders": [order_wire],
        "grouping": "na"
    }


def send_minimal_order():
    if not ENABLE_MAINNET_TRADING:
        print("🛑 Bloccato: ENABLE_MAINNET_TRADING non è true (fail-closed).")
        return False

    print("=== ORDINE MINIMALE HYPERLIQUID ===")

    account = Account.from_key(PRIVATE_KEY)
    print(f"💰 Wallet: {mask_wallet(account.address)}")

    coin = "ETH"
    is_buy = True
    size = 0.01

    # Ottieni prezzo corrente da Hyperliquid
    mid_price = get_mid_price(coin)
    if mid_price:
        price = round(mid_price * 0.95, 2)  # 5% sotto mid per ordine limite
        print(f"📊 Prezzo mid corrente: ${mid_price}")
    else:
        price = 4000
        print(f"⚠️ Impossibile ottenere prezzo mid, uso predefinito: ${price}")

    print(f"📝 Ordine: {coin} {'BUY' if is_buy else 'SELL'} {size} @ ${price}")

    order_action = create_minimal_order(coin, is_buy, size, price)
    if not order_action:
        return False

    print("✅ Azione ordine creata")

    timestamp = get_timestamp_ms()
    print(f"⏰ Nonce: {timestamp}")

    print("🔐 Firma...")
    signature = sign_l1_action_exact(
        wallet=account,
        action=order_action,
        vault_address=None,
        nonce=timestamp,
        expires_after=None,
        is_mainnet=True
    )
    print("✅ Firma generata")

    payload = {
        "action": order_action,
        "nonce": timestamp,
        "signature": signature,
        "vaultAddress": None
    }

    print("\n🚀 INVIO ORDINE REALE...")
    headers = {"Content-Type": "application/json"}
    response = requests.post(f"{BASE_URL}/exchange", json=payload, headers=headers, timeout=EXCHANGE_TIMEOUT)
    print(f"📡 Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        if result.get("status") == "ok":
            print("🎉 Ordine accettato dallo exchange")
            return True
        print("❌ Exchange ha rifiutato l'ordine")
        return False

    print("❌ Errore HTTP nell'invio ordine")
    return False


def verify_wallet_balance():
    print("\n=== VERIFICA SALDO ===")
    payload = {"type": "clearinghouseState", "user": WALLET_ADDRESS}
    response = requests.post(f"{BASE_URL}/info", json=payload, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        data = response.json()
        margin = data.get("marginSummary", {})
        balance = margin.get("accountValue", "0")
        available = margin.get("withdrawable", "0")
        print(f"✅ Saldo: ${balance}")
        print(f"✅ Disponibile: ${available}")
        return True
    print(f"❌ Errore nella verifica saldo: status={response.status_code}")
    return False


def verify_connectivity():
    """Verifica connettività API Hyperliquid."""
    print("\n=== VERIFICA CONNETTIVITÀ HYPERLIQUID ===")
    print(f"URL API: {BASE_URL}")

    # Test endpoint /info
    response = requests.post(f"{BASE_URL}/info", json={"type": "meta"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        meta = response.json()
        print(f"✅ Endpoint /info: {len(meta.get('universe', []))} asset")
    else:
        print(f"❌ Endpoint /info fallito: status={response.status_code}")
        return False

    # Test allMids
    response = requests.post(f"{BASE_URL}/info", json={"type": "allMids"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        mids = response.json()
        print(f"✅ Endpoint allMids: {len(mids)} prezzi")
        for coin in ["BTC", "ETH", "SOL"]:
            if coin in mids:
                print(f"   {coin}: ${mids[coin]}")
    else:
        print(f"❌ Endpoint allMids fallito: status={response.status_code}")
        return False

    return True


if __name__ == "__main__":
    print("=" * 50)
    print("HYPERLIQUID ORDINE MINIMALE")
    print("Ordine singolo con firma EIP-712 corretta")
    print(f"API: {BASE_URL}")
    print("=" * 50)
    print()

    if not ENABLE_MAINNET_TRADING:
        print("🛑 Sicurezza: ENABLE_MAINNET_TRADING=false, ordini reali bloccati.")
    else:
        print("✅ ENABLE_MAINNET_TRADING=true rilevato.")

    verify_connectivity()
    verify_wallet_balance()

    if ENABLE_MAINNET_TRADING and AUTO_CONFIRM_MINIMAL_ORDER:
        print("✅ AUTO_CONFIRM_MINIMAL_ORDER=true: invio automatico abilitato.")
        print("\n" + "=" * 30)
        send_minimal_order()
    elif ENABLE_MAINNET_TRADING and not AUTO_CONFIRM_MINIMAL_ORDER:
        print("\n🛑 AUTO_CONFIRM_MINIMAL_ORDER<dyad-write path="utils/circuit_breaker.py">
HALF_OPEN transition basato su recovery_timeout, quindi il breaker si recupera effettivamente invece di rimanere aperto per sempre.">
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit breaker per chiamate API esterne.
    Previene cascate di fallimenti bloccando temporaneamente quando un servizio è giù.
    Transizioni: CLOSED -> OPEN (dopo threshold fallimenti)
                 OPEN -> HALF_OPEN (dopo che recovery_timeout è trascorso)
                 HALF_OPEN -> CLOSED (alla prima chiamata riuscita) o OPEN (al fallimento)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        expected_exception: type = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exception = expected_exception

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0

    def _maybe_transition_to_half_open(self) -> None:
        """Controlla se è passato abbastanza tempo per provare half-open."""
        if self.state != CircuitState.OPEN:
            return
        if self.last_failure_time is None:
            return
        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.recovery_timeout:
            logger.info(
                f"Circuit '{self.name}' transizione OPEN -> HALF_OPEN "
                f"dopo {elapsed:.1f}s (timeout={self.recovery_timeout}s)"
            )
            self.state = CircuitState.HALF_OPEN
            self.half_open_calls = 0

    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Esegue una funzione attraverso il circuit breaker.

        Raises:
            CircuitBreakerOpenError: Se circuit è aperto e timeout recovery non trascorso
            Exception: Qualsiasi eccezione dalla funzione wrappata
        """
        # Controlla se dovremmo transire da OPEN a HALF_OPEN
        self._maybe_transition_to_half_open()

        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit '{self.name}' è OPEN. "
                f"Riproverà dopo {self.recovery_timeout}s dall'ultimo fallimento."
            )

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                # Troppe chiamate half-open fallite, torna a OPEN
                self.state = CircuitState.OPEN
                self.last_failure_time = time.time()
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' HALF_OPEN max chiamate ({self.half_open_max_calls}) superato, ri-apertura"
                )
            self.half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Gestisce chiamata riuscita."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit '{self.name}' recuperato, HALF_OPEN -> CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

    def _on_failure(self) -> None:
        """Gestisce chiamata fallita."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            logger.warning(
                f"Circuit '{self.name}' CLOSED -> OPEN dopo {self.failure_count} fallimenti consecutivi"
            )
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit '{self.name}' fallito in HALF_OPEN, ri-apertura")
            self.state = CircuitState.OPEN

    def reset(self) -> None:
        """Resetta manualmente il circuit breaker allo stato closed."""
        logger.info(f"Circuit '{self.name}' resettato manualmente a CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

    def get_state(self) -> Dict[str, Any]:
        """Ottieni stato corrente del circuit breaker."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "half_open_calls": self.half_open_calls,
            "recovery_timeout": self.recovery_timeout,
            "failure_threshold": self.failure_threshold
        }


class CircuitBreakerOpenError(Exception):
    """Eccezione sollevata quando circuit breaker è aperto."""
    pass


# Registro globale di circuit breaker
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_or_create_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 3,
    expected_exception: type = Exception
) -> CircuitBreaker:
    """
    Ottieni o crea un circuit breaker per nome.
    Utile per condividere circuit breaker tra moduli.
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            expected_exception=expected_exception
        )
    return _circuit_breakers[name]


def get_all_circuit_states() -> Dict[str, Dict[str, Any]]:
    """Ottieni stati di tutti i circuit breaker."""
    return {name: cb.get_state() for name, cb in _circuit_breakers.items()}