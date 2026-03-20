#!/usr/bin/env python3
"""
Script to close SOL position on Hyperliquid.
Uses configuration from .env file.

Security: Private key is derived into Account immediately and never stored as a raw string.
"""

import os
import time
from decimal import Decimal

import requests
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


def post_info(payload: dict) -> dict:
    response = requests.post(f"{BASE_URL}/info", json=payload, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        return response.json()
    print(f"Error: status={response.status_code}")
    return None


def get_asset_id(coin):
    response = requests.post(f"{BASE_URL}/info", json={"type": "meta"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        meta = response.json()
        for i, asset in enumerate(meta.get("universe", [])):
            if asset.get("name") == coin:
                return i
    return None


def get_mid_price(coin):
    response = requests.post(f"{BASE_URL}/info", json={"type": "allMids"}, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        mids = response.json()
        if coin in mids:
            return float(mids[coin])
    return None


def main():
    print("=== CLOSE SOL POSITION ===")
    print(f"Wallet: {mask_wallet(WALLET_ADDRESS)}")
    print(f"API: {BASE_URL}")
    print()

    if not ACCOUNT:
        print("❌ HYPERLIQUID_PRIVATE_KEY not set or invalid.")
        return

    if not ENABLE_MAINNET_TRADING:
        print("ENABLE_MAINNET_TRADING is false. Cannot close position.")
        return

    # Get current SOL position
    user_state = post_info({"type": "clearinghouseState", "user": WALLET_ADDRESS})
    if not user_state:
        print("Failed to get user state")
        return

    sol_position = None
    for pos_wrapper in user_state.get("assetPositions", []):
        pos = pos_wrapper.get("position", {})
        if pos.get("coin") == "SOL":
            size = Decimal(str(pos.get("szi", "0")))
            if size != 0:
                sol_position = pos
                break

    if not sol_position:
        print("No open SOL position found")
        return

    size = Decimal(str(sol_position.get("szi", "0")))
    entry_px = Decimal(str(sol_position.get("entryPx", "0")))
    pnl = Decimal(str(sol_position.get("unrealizedPnl", "0")))
    side = "LONG" if size > 0 else "SHORT"

    print(f"SOL Position: {side}")
    print(f"  Size: {size}")
    print(f"  Entry: ${entry_px}")
    print(f"  PnL: ${pnl}")

    # Get current price
    mid_price = get_mid_price("SOL")
    if not mid_price:
        print("Failed to get SOL mid price")
        return
    print(f"  Current Price: ${mid_price}")

    # Close position
    close_side = "sell" if size > 0 else "buy"
    close_size = abs(size)
    is_buy = close_side == "buy"

    # Use mid price with small offset for limit order
    if is_buy:
        limit_price = round(mid_price * 1.005, 2)  # Slightly above mid for buy
    else:
        limit_price = round(mid_price * 0.995, 2)  # Slightly below mid for sell

    asset_id = get_asset_id("SOL")
    if asset_id is None:
        print("Failed to get SOL asset ID")
        return

    print(f"\nClosing: {close_side.upper()} {close_size} SOL @ ${limit_price}")

    order_wire = {
        "a": asset_id,
        "b": is_buy,
        "p": str(limit_price),
        "s": str(close_size),
        "r": False,
        "t": {"limit": {"tif": "Gtc"}}
    }

    action = {"type": "order", "orders": [order_wire], "grouping": "na"}
    nonce = int(time.time() * 1000)
    signature = sign_l1_action_exact(ACCOUNT, action, None, nonce, None, True)

    payload = {
        "action": action,
        "nonce": nonce,
        "signature": signature,
        "vaultAddress": None
    }

    print("Sending close order...")
    response = requests.post(
        f"{BASE_URL}/exchange",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=EXCHANGE_TIMEOUT
    )

    if response.status_code == 200:
        result = response.json()
        if result.get("status") == "ok":
            print("SOL position close order accepted!")
        else:
            print(f"Exchange rejected: {result}")
    else:
        print(f"HTTP error: {response.status_code}")


if __name__ == "__main__":
    main()