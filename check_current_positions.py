#!/usr/bin/env python3
"""
Script to check current positions on Hyperliquid.
All data sourced from Hyperliquid API.
"""

import os
import requests
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

WALLET_ADDRESS = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
BASE_URL = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
INFO_TIMEOUT = int(os.getenv("HYPERLIQUID_INFO_TIMEOUT", "15"))


def mask_wallet(wallet: str) -> str:
    if not wallet or len(wallet) < 12:
        return "invalid_wallet"
    return f"{wallet[:6]}...{wallet[-4:]}"


def post_info(payload: dict) -> dict:
    """POST to Hyperliquid /info endpoint."""
    response = requests.post(f"{BASE_URL}/info", json=payload, timeout=INFO_TIMEOUT)
    if response.status_code == 200:
        return response.json()
    print(f"Error: status={response.status_code}")
    return None


def main():
    print("=== HYPERLIQUID POSITION CHECK ===")
    print(f"Wallet: {mask_wallet(WALLET_ADDRESS)}")
    print(f"API: {BASE_URL}")
    print()

    # Get metadata
    print("Fetching metadata...")
    meta = post_info({"type": "meta"})
    if not meta:
        print("❌ Could not fetch metadata")
        return
    print(f"✅ Metadata: {len(meta.get('universe', []))} assets available")

    # Get all mid prices
    print("Fetching mid prices...")
    mids = post_info({"type": "allMids"})
    if mids:
        print(f"✅ Mid prices for {len(mids)} assets")
        top_coins = ["BTC", "ETH", "SOL", "BNB", "ADA"]
        for coin in top_coins:
            if coin in mids:
                print(f"   {coin}: ${mids[coin]}")
    print()

    # Get user state
    print("Fetching user state...")
    user_state = post_info({"type": "clearinghouseState", "user": WALLET_ADDRESS})
    if not user_state:
        print("❌ Could not fetch user state")
        return

    # Display balance
    if "marginSummary" in user_state:
        margin = user_state["marginSummary"]
        total_account_value = Decimal(str(margin.get("accountValue", 0)))
        total_margin_used = Decimal(str(margin.get("totalMarginUsed", 0)))
        withdrawable = Decimal(str(margin.get("withdrawable", 0)))

        print(f"💰 Total Balance: ${total_account_value:.2f}")
        print(f"💳 Available: ${withdrawable:.2f}")
        print(f"📊 Margin Used: ${total_margin_used:.2f}")

        if total_account_value > 0:
            margin_usage = (total_margin_used / total_account_value) * 100
            print(f"📈 Margin Usage: {margin_usage:.1f}%")

    # Display positions
    print("\n📊 CURRENT POSITIONS:")
    positions = user_state.get("assetPositions", [])

    open_positions = 0
    for position in positions:
        position_data = position.get("position", {})
        coin = position_data.get("coin", "Unknown")
        size = Decimal(str(position_data.get("szi", 0)))

        if size != 0:
            open_positions += 1
            entry_px = Decimal(str(position_data.get("entryPx", 0)))
            unrealized_pnl = Decimal(str(position_data.get("unrealizedPnl", 0)))
            margin_used = Decimal(str(position_data.get("marginUsed", 0)))
            position_value = abs(size * entry_px)
            leverage = position_value / margin_used if margin_used > 0 else Decimal("0")

            # Get current mid price
            current_price = Decimal(str(mids.get(coin, "0"))) if mids and coin in mids else entry_px
            current_value = abs(size * current_price)

            print(f"\n   {coin}:")
            print(f"     Type: {'LONG' if size > 0 else 'SHORT'}")
            print(f"     Size: {size} {coin}")
            print(f"     Entry Price: ${entry_px:.2f}")
            print(f"     Current Price: ${current_price:.2f}")
            print(f"     Position Value: ${current_value:.2f}")
            print(f"     Unrealized PnL: ${unrealized_pnl:.4f}")
            print(f"     Margin Used: ${margin_used:.4f}")
            print(f"     Leverage: {leverage:.2f}x")

    if open_positions == 0:
        print("   No open positions")

    # Display funding rates for tracked coins
    print("\n📊 FUNDING RATES:")
    for asset in meta.get("universe", []):
        coin = asset.get("name", "")
        if coin in ["BTC", "ETH", "SOL", "BNB", "ADA"]:
            funding = asset.get("funding", "N/A")
            oi = asset.get("openInterest", "N/A")
            max_lev = asset.get("maxLeverage", "N/A")
            print(f"   {coin}: funding={funding}, OI={oi}, maxLev={max_lev}x")


if __name__ == "__main__":
    main()