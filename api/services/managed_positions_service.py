from decimal import Decimal
from typing import Any, Dict, List


def build_managed_positions_payload(
    exchange_positions: Dict[str, Dict[str, Any]],
    managed_data: Dict[str, Any],
    default_sl_pct: Decimal,
    default_tp_pct: Decimal,
    default_be_activation_pct: Decimal,
    default_trailing_callback: Decimal,
) -> List[Dict[str, Any]]:
    positions_list: List[Dict[str, Any]] = []

    for coin, ex_pos in exchange_positions.items():
        size = Decimal(str(ex_pos.get("size", "0")))
        if size == 0:
            continue

        is_long = size > 0
        abs_size = abs(size)
        entry_price = Decimal(str(ex_pos.get("entry_price", "0")))

        managed_raw = managed_data.get(coin, {})
        sl = managed_raw.get("stop_loss", {})
        tp = managed_raw.get("take_profit", {})
        ts = managed_raw.get("trailing_stop", {})
        be = managed_raw.get("break_even", {})

        sl_pct = Decimal(str(sl.get("percentage", default_sl_pct)))
        tp_pct = Decimal(str(tp.get("percentage", default_tp_pct)))

        sl_price_abs = sl.get("price")
        tp_price_abs = tp.get("price")

        break_even_activated = bool(be.get("activated", False))
        break_even_activation_pct = Decimal(str(be.get("activation_pct", default_be_activation_pct)))

        if break_even_activated and sl_price_abs is not None:
            sl_price = Decimal(str(sl_price_abs))
        elif sl_price_abs is not None:
            sl_price = Decimal(str(sl_price_abs))
        elif entry_price > 0:
            if is_long:
                sl_price = entry_price * (Decimal("1") - sl_pct)
            else:
                sl_price = entry_price * (Decimal("1") + sl_pct)
        else:
            sl_price = Decimal("0")

        if tp_price_abs is not None:
            tp_price = Decimal(str(tp_price_abs))
        elif entry_price > 0:
            if is_long:
                tp_price = entry_price * (Decimal("1") + tp_pct)
            else:
                tp_price = entry_price * (Decimal("1") - tp_pct)
        else:
            tp_price = Decimal("0")

        positions_list.append({
            "coin": coin,
            "side": "LONG" if is_long else "SHORT",
            "size": str(abs_size),
            "entry_price": str(entry_price),
            "stop_loss_price": str(sl_price),
            "stop_loss_pct": str(sl_pct),
            "take_profit_price": str(tp_price),
            "take_profit_pct": str(tp_pct),
            "trailing_enabled": bool(ts.get("enabled", False)),
            "trailing_callback": str(ts.get("callback_rate", default_trailing_callback)),
            "highest_tracked": ts.get("highest_price"),
            "lowest_tracked": ts.get("lowest_price"),
            "break_even_activated": break_even_activated,
            "break_even_activation_pct": str(break_even_activation_pct),
            "opened_at": managed_raw.get("opened_at", 0),
            "source": "managed" if coin in managed_data else "exchange_only",
        })

    positions_list.sort(key=lambda p: p["coin"])
    return positions_list