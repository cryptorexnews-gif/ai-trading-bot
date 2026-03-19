#!/usr/bin/env python3
"""
ORDEN MÍNIMA FUNCIONAL PARA HYPERLIQUID
Script que hace UNA SOLA orden mínima con el esquema EIP-712 correcto
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
BASE_URL = "https://api.hyperliquid.xyz"


def mask_wallet(wallet: str) -> str:
    if not wallet or len(wallet) < 12:
        return "invalid_wallet"
    return f"{wallet[:6]}...{wallet[-4:]}"


def address_to_bytes(address):
    """Convierte dirección Ethereum a bytes"""
    return bytes.fromhex(address[2:].lower())


def action_hash(action, vault_address, nonce, expires_after):
    """Hash de acción - EXACTO como SDK oficial"""
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
    """Agente fantasma - EXACTO como SDK oficial"""
    return {
        "source": "a" if is_mainnet else "b",
        "connectionId": "0x" + hash_bytes.hex()
    }


def l1_payload(phantom_agent):
    """Payload EIP-712 - EXACTO como SDK oficial"""
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
    """sign_l1_action - EXACTA implementación"""
    hash_bytes = action_hash(action, vault_address, nonce, expires_after)
    phantom_agent = construct_phantom_agent(hash_bytes, is_mainnet)
    data = l1_payload(phantom_agent)

    structured_data = encode_typed_data(full_message=data)
    signed = wallet.sign_message(structured_data)

    return {
        "r": hex(signed.r),
        "s": hex(signed.s),
        "v": signed.v
    }


def get_timestamp_ms():
    """Timestamp en milisegundos"""
    return int(time.time() * 1000)


def get_asset_id(coin):
    """Obtiene el asset ID para una moneda"""
    url = f"{BASE_URL}/info"
    response = requests.post(url, json={"type": "meta"}, timeout=15)
    if response.status_code == 200:
        meta = response.json()
        for i, asset in enumerate(meta.get("universe", [])):
            if asset.get("name") == coin:
                return i
    print(f"❌ Error obteniendo asset ID para {coin}: status={response.status_code} (body redacted)")
    return None


def create_minimal_order(coin, is_buy, sz, limit_px):
    """Crea una orden MÍNIMA y FUNCIONAL"""
    asset_id = get_asset_id(coin)
    if asset_id is None:
        print(f"❌ No se encontró asset ID para {coin}")
        return None

    print(f"✅ Asset ID para {coin}: {asset_id}")

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
    """Envía UNA SOLA orden mínima a Hyperliquid"""
    if not ENABLE_MAINNET_TRADING:
        print("🛑 Bloqueado: ENABLE_MAINNET_TRADING no está en true (fail-closed).")
        return False

    print("=== ORDEN MÍNIMA HYPERLIQUID ===")

    account = Account.from_key(PRIVATE_KEY)
    print(f"💰 Wallet: {mask_wallet(account.address)}")

    coin = "ETH"
    is_buy = True
    size = 0.01
    price = 4000

    print(f"📝 Orden: {coin} {'BUY' if is_buy else 'SELL'} {size} @ ${price}")

    order_action = create_minimal_order(coin, is_buy, size, price)
    if not order_action:
        return False

    print("✅ Acción de orden creada")

    timestamp = get_timestamp_ms()
    print(f"⏰ Nonce: {timestamp}")

    print("🔐 Firmando...")
    signature = sign_l1_action_exact(
        wallet=account,
        action=order_action,
        vault_address=None,
        nonce=timestamp,
        expires_after=None,
        is_mainnet=True
    )

    print("✅ Firma generada")

    payload = {
        "action": order_action,
        "nonce": timestamp,
        "signature": signature,
        "vaultAddress": None
    }

    print("\n🚀 ENVIANDO ORDEN REAL...")
    url = f"{BASE_URL}/exchange"
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    print(f"📡 Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        if result.get("status") == "ok":
            print("🎉 Orden aceptada por exchange")
            return True
        print("❌ Exchange rechazó la orden (detalles redacted)")
        return False

    print("❌ Error HTTP al enviar orden (body redacted)")
    return False


def verify_wallet_balance():
    """Verifica el balance de la wallet"""
    print("\n=== VERIFICANDO BALANCE ===")

    url = f"{BASE_URL}/info"
    payload = {
        "type": "clearinghouseState",
        "user": WALLET_ADDRESS
    }

    response = requests.post(url, json=payload, timeout=15)
    if response.status_code == 200:
        data = response.json()
        print("✅ Estado del usuario recibido correctamente")
        print(f"📊 Keys: {list(data.keys())}")
        return True

    print(f"❌ Error al verificar balance: status={response.status_code} (body redacted)")
    return False


if __name__ == "__main__":
    print("=" * 50)
    print("ORDEN MÍNIMA HYPERLIQUID")
    print("Una sola orden funcional con EIP-712 correcto")
    print("=" * 50)
    print()

    if not ENABLE_MAINNET_TRADING:
        print("🛑 Seguridad: ENABLE_MAINNET_TRADING=false, no se permite enviar órdenes reales.")
    else:
        print("✅ ENABLE_MAINNET_TRADING=true detectado.")

    verify_wallet_balance()

    if ENABLE_MAINNET_TRADING:
        expected_suffix = WALLET_ADDRESS[-4:] if WALLET_ADDRESS else ""
        typed_suffix = input(f"\nEscribe los últimos 4 caracteres de tu wallet ({mask_wallet(WALLET_ADDRESS)}) para confirmar: ").strip()

        if typed_suffix != expected_suffix:
            print("🛑 Confirmación fallida. Orden cancelada.")
        elif input("¿Enviar orden mínima REAL a Hyperliquid? (y/n): ").lower() == 'y':
            print("\n" + "=" * 30)
            send_minimal_order()
        else:
            print("\n📋 Orden preparada pero no enviada")
    else:
        print("\n📋 Script en modo seguro: no se enviarán órdenes reales")