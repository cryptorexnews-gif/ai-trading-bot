from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Optional, Tuple


def default_tick_size_for_asset(asset_id: int) -> Tuple[Decimal, int]:
    defaults: Dict[int, Tuple[Decimal, int]] = {
        0: (Decimal("0.1"), 1),
        1: (Decimal("0.01"), 2),
        5: (Decimal("0.001"), 3),
        7: (Decimal("0.01"), 2),
        65: (Decimal("0.00001"), 5),
    }
    return defaults.get(asset_id, (Decimal("0.01"), 2))


def infer_tick_size_and_precision_from_mid(raw_price: str) -> Tuple[Decimal, int]:
    if "." in raw_price:
        right_side = raw_price.rstrip("0").split(".")[1]
        decimals = len(right_side) if right_side else 0
    else:
        decimals = 0

    decimals = max(1, min(decimals, 8))
    tick_size = Decimal("1").scaleb(-decimals) if decimals > 0 else Decimal("1")
    return tick_size, decimals


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
    digits_before_decimal = adjusted + 1 if adjusted >= 0 else 0
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