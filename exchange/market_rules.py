from decimal import Decimal, ROUND_DOWN
from typing import Dict, Tuple


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