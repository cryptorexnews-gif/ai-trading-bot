#!/usr/bin/env python3
"""
MINIMAL ORDER FOR HYPERLIQUID
Script that places ONE minimal order with correct EIP-712 signing.
Uses configuration from .env file.
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
    print(f"❌ Error getting asset ID for {coin}: status={response.status_code}")
    return None


def get_mid_price(coin):
    """Get current mid price from Hyperliquid."""
    response = requests.post(f"{BASE_URL}/info", json={"type": "allMids"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        mids = response.json()
        if coin in mids:
            return float(mids[coin])
    return None


def create_minimal_order(coin, is_buy, sz, limit_px):
    asset_id = get_asset_id(coin)
    if asset_id is None:
        print(f"❌ Asset ID not found for {coin}")
        return None

    print(f"✅ Asset ID for {coin}: {asset_id}")

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
        print("🛑 Blocked: ENABLE_MAINNET_TRADING is not true (fail-closed).")
        return False

    print("=== MINIMAL HYPERLIQUID ORDER ===")

    account = Account.from_key(PRIVATE_KEY)
    print(f"💰 Wallet: {mask_wallet(account.address)}")

    coin = "ETH"
    is_buy = True
    size = 0.01

    # Get current price from Hyperliquid
    mid_price = get_mid_price(coin)
    if mid_price:
        price = round(mid_price * 0.95, 2)  # 5% below mid for limit order
        print(f"📊 Current mid price: ${mid_price}")
    else:
        price = 4000
        print(f"⚠️ Could not get mid price, using default: ${price}")

    print(f"📝 Order: {coin} {'BUY' if is_buy else 'SELL'} {size} @ ${price}")

    order_action = create_minimal_order(coin, is_buy, size, price)
    if not order_action:
        return False

    print("✅ Order action created")

    timestamp = get_timestamp_ms()
    print(f"⏰ Nonce: {timestamp}")

    print("🔐 Signing...")
    signature = sign_l1_action_exact(
        wallet=account,
        action=order_action,
        vault_address=None,
        nonce=timestamp,
        expires_after=None,
        is_mainnet=True
    )
    print("✅ Signature generated")

    payload = {
        "action": order_action,
        "nonce": timestamp,
        "signature": signature,
        "vaultAddress": None
    }

    print("\n🚀 SENDING REAL ORDER...")
    headers = {"Content-Type": "application/json"}
    response = requests.post(f"{BASE_URL}/exchange", json=payload, headers=headers, timeout=EXCHANGE_TIMEOUT)
    print(f"📡 Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        if result.get("status") == "ok":
            print("🎉 Order accepted by exchange")
            return True
        print("❌ Exchange rejected the order")
        return False

    print("❌ HTTP error sending order")
    return False


def verify_wallet_balance():
    print("\n=== VERIFYING BALANCE ===")
    payload = {"type": "clearinghouseState", "user": WALLET_ADDRESS}
    response = requests.post(f"{BASE_URL}/info", json=payload, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        data = response.json()
        margin = data.get("marginSummary", {})
        balance = margin.get("accountValue", "0")
        available = margin.get("withdrawable", "0")
        print(f"✅ Balance: ${balance}")
        print(f"✅ Available: ${available}")
        return True
    print(f"❌ Error verifying balance: status={response.status_code}")
    return False


def verify_connectivity():
    """Verify Hyperliquid API connectivity."""
    print("\n=== VERIFYING HYPERLIQUID CONNECTIVITY ===")
    print(f"API URL: {BASE_URL}")

    # Test /info endpoint
    response = requests.post(f"{BASE_URL}/info", json={"type": "meta"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        meta = response.json()
        print(f"✅ /info endpoint: {len(meta.get('universe', []))} assets")
    else:
        print(f"❌ /info endpoint failed: status={response.status_code}")
        return False

    # Test allMids
    response = requests.post(f"{BASE_URL}/info", json={"type": "allMids"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        mids = response.json()
        print(f"✅ allMids endpoint: {len(mids)} prices")
        for coin in ["BTC", "ETH", "SOL"]:
            if coin in mids:
                print(f"   {coin}: ${mids[coin]}")
    else:
        print(f"❌ allMids endpoint failed: status={response.status_code}")
        return False

    return True


if __name__ == "__main__":
    print("=" * 50)
    print("HYPERLIQUID MINIMAL ORDER")
    print("Single order with correct EIP-712 signing")
    print(f"API: {BASE_URL}")
    print("=" * 50)
    print()

    if not ENABLE_MAINNET_TRADING:
        print("🛑 Safety: ENABLE_MAINNET_TRADING=false, real orders blocked.")
    else:
        print("✅ ENABLE_MAINNET_TRADING=true detected.")

    verify_connectivity()
    verify_wallet_balance()

    if ENABLE_MAINNET_TRADING and AUTO_CONFIRM_MINIMAL_ORDER:
        print("✅ AUTO_CONFIRM_MINIMAL_ORDER=true: automatic send enabled.")
        print("\n" + "=" * 30)
        send_minimal_order()
    elif ENABLE_MAINNET_TRADING and not AUTO_CONFIRM_MINIMAL_ORDER:
        print("\n🛑 AUTO_CONFIRM_MINIMAL_ORDER=false: automatic execution disabled for safety.")
    else:
        print("\n📋 Script in safe mode: no real orders will be sent.")