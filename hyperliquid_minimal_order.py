#!/usr/bin/env python3
"""
ORDINE MINIMALE PER HYPERLIQUID
Script che piazza UN ordine minimo con firma EIP-712 corretta.
Usa configurazione da .env file.

Security: Private key is derived into Account immediately and never stored as a raw string.
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

# Security: Derive Account immediately, raw key is not stored
_raw_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
ACCOUNT = Account.from_key(_raw_key) if _raw_key else None
del _raw_key  # Remove raw key from module scope

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
    if not ACCOUNT:
        print("🛑 Bloccato: HYPERLIQUID_PRIVATE_KEY non configurata o invalida.")
        return False

    if not ENABLE_MAINNET_TRADING:
        print("🛑 Bloccato: ENABLE_MAINNET_TRADING non è true (fail-closed).")
        return False

    print("=== ORDINE MINIMALE HYPERLIQUID ===")

    print(f"💰 Wallet: {mask_wallet(ACCOUNT.address)}")

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
        wallet=ACCOUNT,
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
        available = data.get("withdrawable", margin.get("withdrawable", "0"))
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

    if not ACCOUNT:
        print("🛑 Errore: HYPERLIQUID_PRIVATE_KEY non configurata.")
    elif not ENABLE_MAINNET_TRADING:
        print("🛑 Sicurezza: ENABLE_MAINNET_TRADING=false, ordini reali bloccati.")
    else:
        print(f"✅ ENABLE_MAINNET_TRADING=true rilevato. Wallet: {mask_wallet(ACCOUNT.address)}")

    verify_connectivity()
    verify_wallet_balance()

    if ACCOUNT and ENABLE_MAINNET_TRADING and AUTO_CONFIRM_MINIMAL_ORDER:
        print("✅ AUTO_CONFIRM_MINIMAL_ORDER=true: invio automatico abilitato.")
        print("\n" + "=" * 30)
        send_minimal_order()
    elif ACCOUNT and ENABLE_MAINNET_TRADING and not AUTO_CONFIRM_MINIMAL_ORDER:
        print("\n🛑 AUTO_CONFIRM_MINIMAL_ORDER=false.")
        print("Per inviare l'ordine, imposta AUTO_CONFIRM_MINIMAL_ORDER=true nel .env")
    else:
        print("\n📋 Verifica completata. Nessun ordine inviato.")