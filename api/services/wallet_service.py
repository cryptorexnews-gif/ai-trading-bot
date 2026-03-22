import os


def get_wallet_address() -> str:
    return os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()


def has_wallet_configured() -> bool:
    return bool(get_wallet_address())