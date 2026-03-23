from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Optional, Tuple


# Known tick sizes for major assets on Hyperliquid.
# IMPORTANT: Trigger orders (TP/SL) require these tick sizes.
# Limit orders may accept finer granularity but trigger orders do NOT.
# Verified against live Hyperliquid exchange behavior.
KNOWN_TICK_SIZES: Dict[str, Tuple[Decimal, int]] = {
    "BTC": (Decimal("1"), 0),        # $100k+ → tick=1, 0 decimals
    "ETH": (Decimal("1"), 0),        # $2k+ → tick=1, 0 decimals (trigger orders require integer)
    "SOL": (Decimal("0.01"), 2),     # $100-$999 → tick=0.01, 2 decimals
    "BNB": (Decimal("0.01"), 2),
    "XRP": (Decimal("0.0001"), 4),
    "ADA": (Decimal("0.0001"), 4),
    "DOGE": (Decimal("0.00001"), 5),
    "AVAX": (Decimal("0.01"), 2),
    "LINK": (Decimal("0.001"), 3),
    "SUI": (Decimal("0.0001"), 4),
    "ARB": (Decimal("0.0001"), 4),
    "OP": (Decimal("0.001"), 3),
    "NEAR": (Decimal("0.001"), 3),
    "WIF": (Decimal("0.0001"), 4),
    "PEPE": (Decimal("0.0000001"), 7),
    "INJ": (Decimal("0.01"), 2),
    "TIA": (Decimal("0.001"), 3),
    "SEI": (Decimal("0.0001"), 4),
    "RENDER": (Decimal("0.001"), 3),
    "FET": (Decimal("0.0001"), 4),
}


def default_tick_size_for_asset(asset_id: int) -> Tuple[Decimal, int]:
    defaults: Dict[int, Tuple[Decimal, int]] = {
        0: (Decimal("1"), 0),         # BTC
        1: (Decimal("1"), 0),         # ETH
        5: (Decimal("0.001"), 3),
        7: (Decimal("0.01"), 2),
        65: (Decimal("0.00001"), 5),
    }
    return defaults.get(asset_id, (Decimal("0.01"), 2))


def get_tick_size_for_known_coin(coin: str) -> Optional[Tuple[Decimal, int]]:
    """Return known tick size for a coin, or None if not in the table."""
    return KNOWN_TICK_SIZES.get(str(coin or "").strip().upper())


def infer_tick_size_from_price(price: Decimal, max_sig_figs: int = 5) -> Tuple[Decimal, int]:
    """
    Hyperliquid rule: prices must have at most 5 significant figures.
    Given a price, compute the tick size and number of decimals allowed.

    Examples:
      price=2048.75 → 4 digits before decimal → 5-4=1 decimal → tick=0.1
      price=150.25  → 3 digits before decimal → 5-3=2 decimals → tick=0.01
      price=0.5432  → 0 digits before decimal → 5-0=5 decimals → tick=0.00001
      price=105000   → 6 digits before decimal → 5-6=0 decimals → tick=1 (or 10)
    """
    if price <= 0:
        return Decimal("0.01"), 2

    # Count digits before decimal point
    adjusted = price.normalize().adjusted()
    digits_before_decimal = max(0, adjusted + 1)

    # Decimals allowed = max_sig_figs - digits_before_decimal
    decimals = max(0, max_sig_figs - digits_before_decimal)

    tick_size = Decimal("1").scaleb(-decimals) if decimals > 0 else Decimal("1")
    return tick_size, decimals


def infer_tick_size_and_precision_from_mid(raw_price: str) -> Tuple[Decimal, int]:
    """
    Infer tick size from a mid price string using the 5 significant figures rule.
    """
    try:
        price = Decimal(str(raw_price))
    except Exception:
        return Decimal("0.01"), 2

    if price <= 0:
        return Decimal("0.01"), 2

    return infer_tick_size_from_price(price, max_sig_figs=5)


def normalize_size_for_decimals(size: Decimal, sz_decimals: int) -> Decimal:
    if size <= 0:
        return Decimal("0")
    if sz_decimals is None or sz_decimals < 0:
        return size

    step = Decimal("1").scaleb(-sz_decimals)
    normalized = (size / step).to_integral_value(rounding=ROUND_DOWN) * step
    if normalized <= 0:
        normalized = step
    return normalized


def get_max_price_decimals_from_sz(sz_decimals: Optional[int], max_decimals_perp: int = 6) -> int:
    """
    Hyperliquid perp rule fallback:
    max decimali prezzo = 6 - szDecimals

    WARNING: This is a rough heuristic. Prefer infer_tick_size_from_price() or
    KNOWN_TICK_SIZES for accurate results.
    """
    if sz_decimals is None:
        return 2
    return max(0, int(max_decimals_perp) - int(sz_decimals))


def get_sigfig_limited_decimals(price: Decimal, max_sigfigs: int = 5) -> int:
    """
    Decimali massimi consentiti per rispettare il limite di significant figures.
    """
    if price <= 0:
        return 0

    adjusted = price.normalize().adjusted()
    digits_before_decimal = max(0, adjusted + 1)
    return max(0, int(max_sigfigs) - digits_before_decimal)


def get_effective_price_decimals(price: Decimal, sz_decimals: Optional[int]) -> int:
    """
    Decimali effettivi = min(limite sig-fig, limite da szDecimals).
    """
    sigfig_decimals = get_sigfig_limited_decimals(price, max_sigfigs=5)
    max_decimals_by_sz = get_max_price_decimals_from_sz(sz_decimals, max_decimals_perp=6)
    return min(sigfig_decimals, max_decimals_by_sz)


def format_price_for_hyperliquid(price: Decimal, sz_decimals: Optional[int]) -> str:
    """
    Formatta prezzo per Hyperliquid in modo robusto:
    - limite significant figures (5)
    - limite decimali prezzo da szDecimals (6 - szDecimals, perp fallback)
    """
    if price <= 0:
        return "0"

    decimals = get_effective_price_decimals(price, sz_decimals)
    quantizer = Decimal("1").scaleb(-decimals) if decimals > 0 else Decimal("1")
    rounded = price.quantize(quantizer, rounding=ROUND_HALF_UP)

    if decimals > 0:
        return f"{rounded:.{decimals}f}"
    return f"{rounded:.0f}"