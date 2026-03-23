#!/usr/bin/env python3
"""
Test live sequenziale:
1) apertura posizione
2) attesa conferma posizione
3) creazione TP/SL con upsert_protective_orders

ATTENZIONE: usa soldi reali se ENABLE_MAINNET_TRADING=true.
"""

import json
import logging
import os
import sys
import time
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from eth_account import Account

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from exchange.market_rules import get_tick_size_for_known_coin, infer_tick_size_from_price, normalize_size_for_decimals
from exchange_client import HyperliquidExchangeClient
from utils.hyperliquid_state import get_open_positions

load_dotenv()

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("live_sequential_entry_tpsl")


def d(key: str, default: str) -> Decimal:
    return Decimal(str(os.getenv(key, default)))


def mask_wallet(wallet: str) -> str:
    if not wallet or len(wallet) < 12:
        return "invalid_wallet"
    return f"{wallet[:6]}...{wallet[-4:]}"


def _asset_int(asset: Dict, keys: List[str]) -> Optional[int]:
    for key in keys:
        if key not in asset:
            continue
        raw = asset.get(key)
        if raw is None:
            continue
        try:
            return int(str(raw))
        except (TypeError, ValueError):
            continue
    return None


def get_asset_precision_from_meta(
    client: HyperliquidExchangeClient, coin: str, mid_price: Decimal
) -> Tuple[Decimal, Decimal, int, int]:
    meta = client.get_meta(force_refresh=True)
    if not isinstance(meta, dict):
        raise RuntimeError("Metadati Hyperliquid non disponibili o formato invalido")

    universe = meta.get("universe", [])
    if not isinstance(universe, list):
        raise RuntimeError("Metadati mancanti: 'universe' non trovato")

    for asset in universe:
        if str(asset.get("name", "")).strip().upper() != coin.upper():
            continue

        logger.info(f"{coin} FULL METADATA DUMP: {json.dumps(asset, indent=2, default=str)}")

        sz_decimals = _asset_int(asset, ["szDecimals", "sizeDecimals", "qtyDecimals"])
        px_decimals = _asset_int(asset, ["pxDecimals", "priceDecimals", "pricePrecision"])

        if sz_decimals is None:
            raise RuntimeError(f"szDecimals mancanti per {coin} nel metadata")

        if px_decimals is not None and px_decimals >= 0:
            logger.info(f"{coin}: pxDecimals from metadata = {px_decimals}")
        else:
            known = get_tick_size_for_known_coin(coin)
            if known is not None:
                tick_size, px_decimals = known
                logger.info(f"{coin}: tick size from known table: tick={tick_size}, px_decimals={px_decimals}")
            else:
                tick_size, px_decimals = infer_tick_size_from_price(mid_price, max_sig_figs=5)
                logger.info(
                    f"{coin}: pxDecimals inferred from mid ${mid_price} using 5 sig figs: "
                    f"tick={tick_size}, px_decimals={px_decimals}"
                )

        tick_size = Decimal("1").scaleb(-px_decimals) if px_decimals > 0 else Decimal("1")
        step_size = Decimal("1").scaleb(-sz_decimals) if sz_decimals > 0 else Decimal("1")
        return tick_size, step_size, px_decimals, sz_decimals

    raise RuntimeError(f"Asset {coin} non trovato nel metadata")


def snap_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    if price <= 0 or tick_size <= 0:
        return Decimal("0")
    units = (price / tick_size).to_integral_value(rounding=ROUND_HALF_UP)
    return units * tick_size


def quantize_to_step(size: Decimal, sz_decimals: int) -> Decimal:
    normalized = normalize_size_for_decimals(size, sz_decimals)
    if normalized <= 0:
        return Decimal("0")
    if sz_decimals > 0:
        q = Decimal("1").scaleb(-sz_decimals)
        return normalized.quantize(q)
    return normalized.quantize(Decimal("1"))


def get_position_size(client: HyperliquidExchangeClient, trading_user: str, coin: str) -> Decimal:
    user_state = client.get_user_state(trading_user)
    if not isinstance(user_state, dict):
        return Decimal("0")
    positions = get_open_positions(user_state)
    pos = positions.get(coin, {})
    return Decimal(str(pos.get("size", "0")))


def wait_position_delta_confirmation(
    client: HyperliquidExchangeClient,
    trading_user: str,
    coin: str,
    size_before: Decimal,
    side: str,
    min_abs_delta: Decimal,
    attempts: int,
    sleep_sec: float,
) -> Tuple[bool, Decimal]:
    is_buy = side == "buy"

    for attempt in range(1, attempts + 1):
        current_size = get_position_size(client, trading_user, coin)
        delta = current_size - size_before

        if is_buy and delta >= min_abs_delta:
            return True, current_size
        if (not is_buy) and delta <= -min_abs_delta:
            return True, current_size

        time.sleep(sleep_sec)

    return False, get_position_size(client, trading_user, coin)


def normalize_size_for_min_notional(
    raw_size: Decimal,
    mid_price: Decimal,
    min_notional_usd: Decimal,
    sz_decimals: int,
) -> Decimal:
    if mid_price <= 0:
        return Decimal("0")

    size = normalize_size_for_decimals(raw_size, sz_decimals)
    if size <= 0:
        return Decimal("0")

    if size * mid_price >= min_notional_usd:
        return size

    required_size = min_notional_usd / mid_price
    size = normalize_size_for_decimals(required_size, sz_decimals)

    if size * mid_price < min_notional_usd and sz_decimals >= 0:
        step = Decimal("1").scaleb(-sz_decimals)
        size = size + step

    return size


def round_trigger_price(price: Decimal, tick_size: Decimal, px_decimals: int) -> Decimal:
    """
    Round trigger price to tick and ensure max 5 significant figures.
    For safety, also ensure the string representation has <= px_decimals decimal places.
    """
    snapped = snap_to_tick(price, tick_size)

    # Verify significant figures count
    # Convert to string and count sig figs
    plain = format(snapped, "f")
    # Remove leading zeros and decimal point for sig fig counting
    stripped = plain.lstrip("0").replace(".", "")
    if not stripped:
        stripped = "0"
    sig_figs = len(stripped.lstrip("0")) if stripped != "0" else 1

    if sig_figs > 5:
        # Need to reduce precision - round to fewer decimals
        new_decimals = max(0, px_decimals - (sig_figs - 5))
        quantizer = Decimal("1").scaleb(-new_decimals) if new_decimals > 0 else Decimal("1")
        snapped = snapped.quantize(quantizer, rounding=ROUND_HALF_UP)

    return snapped


def format_trigger_price(price: Decimal, px_decimals: int) -> str:
    """Format trigger price with exact decimal places."""
    if px_decimals > 0:
        return f"{price:.{px_decimals}f}"
    return f"{price:.0f}"


def test_trigger_order_directly(
    client: HyperliquidExchangeClient,
    coin: str,
    trigger_price: Decimal,
    size: Decimal,
    is_long: bool,
    tpsl: str,
    px_decimals: int,
) -> Dict:
    """
    Test a single trigger order with detailed logging of the exact payload.
    """
    close_side = "sell" if is_long else "buy"

    trigger_wire = format_trigger_price(trigger_price, px_decimals)
    sz_decimals = client.get_sz_decimals(coin)
    if sz_decimals is not None and sz_decimals > 0:
        size_wire = f"{size:.{sz_decimals}f}"
    else:
        size_wire = str(size)

    logger.info(
        f"TEST TRIGGER ORDER: {coin} {tpsl.upper()} {close_side.upper()} "
        f"trigger={trigger_price} -> wire='{trigger_wire}' "
        f"size={size} -> wire='{size_wire}' "
        f"px_decimals={px_decimals}"
    )

    result = client.place_trigger_order(
        coin=coin,
        side=close_side,
        size=size,
        trigger_price=trigger_price,
        tpsl=tpsl,
        reduce_only=True,
        is_market=True,
    )

    logger.info(f"TRIGGER ORDER RESULT: {json.dumps(result, indent=2, default=str)}")
    return result


def main() -> None:
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
    env_wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    base_url = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
    execution_mode = os.getenv("EXECUTION_MODE", "live").lower()
    enable_mainnet = os.getenv("ENABLE_MAINNET_TRADING", "false").lower() == "true"

    if not private_key:
        raise RuntimeError("HYPERLIQUID_PRIVATE_KEY mancante")
    if not env_wallet:
        raise RuntimeError("HYPERLIQUID_WALLET_ADDRESS mancante")
    if execution_mode != "live":
        raise RuntimeError("EXECUTION_MODE deve essere 'live' per questo test")
    if not enable_mainnet:
        raise RuntimeError("ENABLE_MAINNET_TRADING deve essere true per questo test")

    derived = Account.from_key(private_key).address
    if derived.lower() != env_wallet.lower():
        raise RuntimeError(f"Mismatch key/address: derived={derived} env={env_wallet}. Correggi .env")

    coin = os.getenv("TEST_COIN", "ETH").strip().upper()
    side = os.getenv("TEST_SIDE", "buy").strip().lower()
    if side not in {"buy", "sell"}:
        raise RuntimeError("TEST_SIDE invalido: usare 'buy' o 'sell'")

    margin_usd = d("TEST_MARGIN_USD", "2")
    leverage = int(d("TEST_LEVERAGE", "5"))
    sl_pct = d("TEST_SL_PCT", "0.03")
    tp_pct = d("TEST_TP_PCT", "0.06")
    ioc_buffer_pct = d("TEST_IOC_BUFFER_PCT", "0.01")
    min_notional_usd = d("TEST_MIN_NOTIONAL_USD", "10.5")

    entry_confirm_attempts = int(os.getenv("TEST_ENTRY_CONFIRM_ATTEMPTS", "20"))
    entry_confirm_sleep_sec = float(os.getenv("TEST_ENTRY_CONFIRM_SLEEP_SEC", "1"))

    logger.warning("TEST LIVE REALE ATTIVO: questo script può aprire una posizione con soldi reali")
    logger.info(
        f"Wallet diagnostics: derived={mask_wallet(derived)} env={mask_wallet(env_wallet)} | "
        f"coin={coin} side={side} margin={margin_usd} lev={leverage}"
    )

    client = HyperliquidExchangeClient(
        base_url=base_url,
        private_key=private_key,
        enable_mainnet_trading=enable_mainnet,
        execution_mode=execution_mode,
    )

    mids = client.get_all_mids(force_refresh=True)
    if not isinstance(mids, dict) or coin not in mids:
        raise RuntimeError(f"Mid price non disponibile per {coin}")
    mid_price = Decimal(str(mids[coin]))

    tick_size, step_size, px_decimals, sz_decimals = get_asset_precision_from_meta(client, coin, mid_price)
    logger.info(
        f"{coin} FINAL PRECISION: mid={mid_price} tick={tick_size} step={step_size} "
        f"px_decimals={px_decimals} sz_decimals={sz_decimals}"
    )

    # ── DIAGNOSTIC: Test what tick size the exchange_client resolves ──
    asset_id = client.get_asset_id(coin)
    if asset_id is not None:
        client_tick, client_precision = client.get_tick_size_and_precision(asset_id)
        logger.info(
            f"{coin} EXCHANGE CLIENT tick resolution: tick={client_tick}, precision={client_precision} "
            f"(asset_id={asset_id})"
        )
    # ──────────────────────────────────────────────────────────────────

    max_leverage = client.get_max_leverage(coin)
    if leverage > max_leverage:
        leverage = max_leverage
        logger.info(f"Leverage ridotta al massimo consentito: {leverage}")

    if not client.set_leverage(coin, leverage):
        raise RuntimeError(f"Impossibile impostare leverage su {coin}")

    notional_usd = margin_usd * Decimal(str(leverage))
    raw_size = notional_usd / mid_price
    normalized_size = normalize_size_for_min_notional(raw_size, mid_price, min_notional_usd, sz_decimals)
    normalized_size = quantize_to_step(normalized_size, sz_decimals)
    if normalized_size <= 0:
        raise RuntimeError("Size normalizzata non valida")

    trading_user = client.get_trading_user_address()
    size_before = get_position_size(client, trading_user, coin)
    logger.info(f"{coin} position size BEFORE entry: {size_before}")

    if side == "buy":
        raw_entry = mid_price * (Decimal("1") + ioc_buffer_pct)
    else:
        raw_entry = mid_price * (Decimal("1") - ioc_buffer_pct)

    desired_price = snap_to_tick(raw_entry, tick_size)

    if px_decimals > 0:
        price_str = f"{desired_price:.{px_decimals}f}"
    else:
        price_str = f"{desired_price:.0f}"

    logger.info(
        f"ENTRY ORDER: {side.upper()} {normalized_size} {coin} @ {price_str} "
        f"(raw={raw_entry}, snapped={desired_price}, tick={tick_size}, px_dec={px_decimals})"
    )

    entry_result = client.place_order(
        coin=coin, side=side, size=normalized_size,
        desired_price=desired_price, reduce_only=False
    )
    if not entry_result.get("success"):
        raise RuntimeError(f"Entry fallita: {entry_result}")

    filled_price = Decimal(str(entry_result.get("filled_price", desired_price)))

    confirmed, size_after = wait_position_delta_confirmation(
        client=client,
        trading_user=trading_user,
        coin=coin,
        size_before=size_before,
        side=side,
        min_abs_delta=normalized_size * Decimal("0.8"),
        attempts=entry_confirm_attempts,
        sleep_sec=entry_confirm_sleep_sec,
    )
    if not confirmed:
        raise RuntimeError(f"Entry non confermata: before={size_before}, after={size_after}")

    logger.info(f"{coin} position size AFTER entry: {size_after} (before={size_before})")

    actual_delta = abs(size_after) - abs(size_before)
    if actual_delta <= 0:
        actual_delta = normalized_size

    position_size_to_protect = quantize_to_step(actual_delta, sz_decimals)

    logger.info(
        f"{coin} PROTECTION SIZE CALCULATION: "
        f"size_before={size_before}, size_after={size_after}, "
        f"actual_delta={actual_delta}, protection_size={position_size_to_protect}"
    )

    is_long = side == "buy"
    if is_long:
        raw_sl = filled_price * (Decimal("1") - sl_pct)
        raw_tp = filled_price * (Decimal("1") + tp_pct)
    else:
        raw_sl = filled_price * (Decimal("1") + sl_pct)
        raw_tp = filled_price * (Decimal("1") - tp_pct)

    sl_price = round_trigger_price(raw_sl, tick_size, px_decimals)
    tp_price = round_trigger_price(raw_tp, tick_size, px_decimals)

    sl_wire = format_trigger_price(sl_price, px_decimals)
    tp_wire = format_trigger_price(tp_price, px_decimals)

    logger.info(
        f"PROTECTIVE ORDERS DIAGNOSTIC:\n"
        f"  filled_price={filled_price}\n"
        f"  raw_sl={raw_sl} -> snapped={sl_price} -> wire='{sl_wire}'\n"
        f"  raw_tp={raw_tp} -> snapped={tp_price} -> wire='{tp_wire}'\n"
        f"  size={position_size_to_protect} is_long={is_long}\n"
        f"  tick={tick_size} px_decimals={px_decimals}"
    )

    # ── DIAGNOSTIC: Try SL trigger order directly first ──
    logger.info("=" * 50)
    logger.info("DIAGNOSTIC: Testing SL trigger order directly...")
    sl_test = test_trigger_order_directly(
        client=client,
        coin=coin,
        trigger_price=sl_price,
        size=position_size_to_protect,
        is_long=is_long,
        tpsl="sl",
        px_decimals=px_decimals,
    )

    if sl_test.get("success"):
        logger.info("SL trigger order succeeded directly!")

        logger.info("DIAGNOSTIC: Testing TP trigger order directly...")
        tp_test = test_trigger_order_directly(
            client=client,
            coin=coin,
            trigger_price=tp_price,
            size=position_size_to_protect,
            is_long=is_long,
            tpsl="tp",
            px_decimals=px_decimals,
        )

        if tp_test.get("success"):
            logger.info(
                f"BOTH PROTECTIVE ORDERS SUCCEEDED!\n"
                f"  SL oid={sl_test.get('order_id')}\n"
                f"  TP oid={tp_test.get('order_id')}"
            )
        else:
            logger.error(f"TP trigger order failed: {tp_test}")
    else:
        logger.error(f"SL trigger order failed: {sl_test}")

        # Try with integer prices as diagnostic
        sl_int = snap_to_tick(raw_sl, Decimal("1"))
        tp_int = snap_to_tick(raw_tp, Decimal("1"))
        logger.info(
            f"DIAGNOSTIC: Retrying with INTEGER trigger prices: SL={sl_int} TP={tp_int}"
        )

        sl_test_int = test_trigger_order_directly(
            client=client,
            coin=coin,
            trigger_price=sl_int,
            size=position_size_to_protect,
            is_long=is_long,
            tpsl="sl",
            px_decimals=0,
        )
        logger.info(f"SL with integer price result: {sl_test_int}")


if __name__ == "__main__":
    main()