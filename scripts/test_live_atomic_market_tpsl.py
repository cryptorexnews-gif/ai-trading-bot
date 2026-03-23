#!/usr/bin/env python3
"""
Test live atomico:
apertura posizione + stop loss + take profit in un unico batch request
con grouping='positionTpsl'.

ATTENZIONE: usa soldi reali se ENABLE_MAINNET_TRADING=true.

Configurazione via .env:
- HYPERLIQUID_PRIVATE_KEY
- HYPERLIQUID_WALLET_ADDRESS
- EXECUTION_MODE=live
- ENABLE_MAINNET_TRADING=true

Parametri test (opzionali):
- TEST_COIN=ETH
- TEST_SIDE=buy                  # buy (long) o sell (short)
- TEST_MARGIN_USD=2
- TEST_LEVERAGE=5
- TEST_SL_PCT=0.03
- TEST_TP_PCT=0.06
- TEST_IOC_BUFFER_PCT=0.01
- TEST_MIN_NOTIONAL_USD=10.5
- TEST_ENTRY_CONFIRM_ATTEMPTS=20
- TEST_ENTRY_CONFIRM_SLEEP_SEC=1
- TEST_ORDERS_CONFIRM_ATTEMPTS=15
- TEST_ORDERS_CONFIRM_SLEEP_SEC=1
"""

import json
import logging
import os
import sys
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from eth_account import Account

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from exchange.market_rules import normalize_size_for_decimals
from exchange_client import HyperliquidExchangeClient
from utils.hyperliquid_state import get_open_positions

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("live_atomic_entry_tpsl")


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


def get_asset_precision_from_meta(client: HyperliquidExchangeClient, coin: str) -> Tuple[Decimal, Decimal, int, int]:
    """
    Restituisce:
      tick_size, step_size, px_decimals, sz_decimals
    usando i metadata Hyperliquid (source of truth).
    """
    meta = client.get_meta(force_refresh=True)
    if not isinstance(meta, dict):
        raise RuntimeError("Metadati Hyperliquid non disponibili o formato invalido")

    universe = meta.get("universe", [])
    if not isinstance(universe, list):
        raise RuntimeError("Metadati mancanti: 'universe' non trovato")

    for asset in universe:
        if str(asset.get("name", "")).strip().upper() != coin.upper():
            continue

        px_decimals = _asset_int(asset, ["pxDecimals", "priceDecimals", "pricePrecision"])
        sz_decimals = _asset_int(asset, ["szDecimals", "sizeDecimals", "qtyDecimals"])

        if px_decimals is None or sz_decimals is None:
            logger.error(f"Asset metadata per {coin}: {json.dumps(asset, indent=2)}")
            raise RuntimeError(f"Decimali mancanti per {coin} nel metadata")

        if px_decimals < 0 or sz_decimals < 0:
            raise RuntimeError(f"Decimali negativi per {coin}: px={px_decimals}, sz={sz_decimals}")

        tick_size = Decimal("1").scaleb(-px_decimals) if px_decimals > 0 else Decimal("1")
        step_size = Decimal("1").scaleb(-sz_decimals) if sz_decimals > 0 else Decimal("1")
        return tick_size, step_size, px_decimals, sz_decimals

    raise RuntimeError(f"Asset {coin} non trovato nel metadata")


def quantize_to_tick(price: Decimal, tick_size: Decimal, decimals: int) -> Decimal:
    if price <= 0:
        return Decimal("0")
    units = (price / tick_size).to_integral_value(rounding=ROUND_HALF_UP)
    rounded = units * tick_size
    if decimals > 0:
        q = Decimal("1").scaleb(-decimals)
        rounded = rounded.quantize(q)
    return rounded


def format_price_for_tick(price: Decimal, tick_size: Decimal, decimals: int) -> str:
    rounded = quantize_to_tick(price, tick_size, decimals)
    return f"{rounded:.{decimals}f}" if decimals > 0 else f"{rounded:.0f}"


def quantize_to_step(size: Decimal, step_size: Decimal, sz_decimals: int) -> Decimal:
    normalized = normalize_size_for_decimals(size, sz_decimals)
    if normalized <= 0:
        return Decimal("0")
    if sz_decimals > 0:
        q = Decimal("1").scaleb(-sz_decimals)
        return normalized.quantize(q)
    return normalized.quantize(Decimal("1"))


def format_size_for_step(size: Decimal, step_size: Decimal, sz_decimals: int) -> str:
    normalized = quantize_to_step(size, step_size, sz_decimals)
    if sz_decimals > 0:
        return f"{normalized:.{sz_decimals}f}"
    return f"{normalized:.0f}"


def get_position_size(client: HyperliquidExchangeClient, trading_user: str, coin: str) -> Decimal:
    user_state = client.get_user_state(trading_user)
    if not isinstance(user_state, dict):
        return Decimal("0")
    positions = get_open_positions(user_state)
    pos = positions.get(coin, {})
    return Decimal(str(pos.get("size", "0")))


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

    current_notional = size * mid_price
    if current_notional >= min_notional_usd:
        return size

    required_size = min_notional_usd / mid_price
    size = normalize_size_for_decimals(required_size, sz_decimals)

    if size * mid_price < min_notional_usd and sz_decimals >= 0:
        step = Decimal("1").scaleb(-sz_decimals)
        size = size + step

    return size


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
            logger.info(
                f"Conferma entry BUY ({attempt}/{attempts}): "
                f"before={size_before}, now={current_size}, delta={delta}"
            )
            return True, current_size

        if (not is_buy) and delta <= -min_abs_delta:
            logger.info(
                f"Conferma entry SELL ({attempt}/{attempts}): "
                f"before={size_before}, now={current_size}, delta={delta}"
            )
            return True, current_size

        time.sleep(sleep_sec)

    return False, get_position_size(client, trading_user, coin)


def _extract_order_tpsl(order: Dict) -> str:
    direct = str(order.get("tpsl", "")).strip().lower()
    if direct in {"tp", "sl"}:
        return direct

    trigger = order.get("trigger", {})
    if isinstance(trigger, dict):
        t = str(trigger.get("tpsl", "")).strip().lower()
        if t in {"tp", "sl"}:
            return t

    order_type = order.get("orderType", {})
    if isinstance(order_type, dict):
        trigger2 = order_type.get("trigger", {})
        if isinstance(trigger2, dict):
            t = str(trigger2.get("tpsl", "")).strip().lower()
            if t in {"tp", "sl"}:
                return t

    nested = order.get("order", {})
    if isinstance(nested, dict):
        t = str(nested.get("tpsl", "")).strip().lower()
        if t in {"tp", "sl"}:
            return t
        nested_trigger = nested.get("trigger", {})
        if isinstance(nested_trigger, dict):
            t2 = str(nested_trigger.get("tpsl", "")).strip().lower()
            if t2 in {"tp", "sl"}:
                return t2

    if bool(order.get("isTp")):
        return "tp"
    if bool(order.get("isSl")):
        return "sl"

    return ""


def _extract_order_coin(order: Dict) -> str:
    coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
    if coin:
        return coin
    nested = order.get("order", {})
    if isinstance(nested, dict):
        return str(nested.get("coin", nested.get("symbol", ""))).strip().upper()
    return ""


def _extract_order_side(order: Dict) -> str:
    def norm(v) -> str:
        raw = str(v or "").strip().lower()
        if raw in {"b", "buy", "bid", "long", "true"}:
            return "buy"
        if raw in {"a", "s", "sell", "ask", "short", "false"}:
            return "sell"
        return ""

    for candidate in [order.get("side"), order.get("dir"), order.get("b")]:
        n = norm(candidate)
        if n:
            return n

    nested = order.get("order", {})
    if isinstance(nested, dict):
        for candidate in [nested.get("side"), nested.get("dir"), nested.get("b")]:
            n = norm(candidate)
            if n:
                return n

    return ""


def _extract_reduce_only(order: Dict) -> bool:
    for candidate in [order.get("r"), order.get("reduceOnly"), order.get("isReduceOnly")]:
        if isinstance(candidate, bool) and candidate:
            return True
        if str(candidate).strip().lower() in {"true", "1"}:
            return True

    nested = order.get("order", {})
    if isinstance(nested, dict):
        for candidate in [nested.get("r"), nested.get("reduceOnly"), nested.get("isReduceOnly")]:
            if isinstance(candidate, bool) and candidate:
                return True
            if str(candidate).strip().lower() in {"true", "1"}:
                return True

    return False


def wait_protective_orders_confirmation(
    client: HyperliquidExchangeClient,
    trading_user: str,
    coin: str,
    close_side: str,
    attempts: int,
    sleep_sec: float,
) -> Tuple[bool, int, int, List[int]]:
    for attempt in range(1, attempts + 1):
        open_orders = client.get_open_orders(trading_user, force_refresh=True)

        tp_count = 0
        sl_count = 0
        protective_oids: List[int] = []

        for order in open_orders:
            if not isinstance(order, dict):
                continue
            if _extract_order_coin(order) != coin:
                continue
            if _extract_order_side(order) != close_side:
                continue
            if not _extract_reduce_only(order):
                continue

            tpsl = _extract_order_tpsl(order)
            if tpsl == "tp":
                tp_count += 1
            elif tpsl == "sl":
                sl_count += 1

            oid = order.get("oid")
            if oid is None:
                nested = order.get("order", {})
                if isinstance(nested, dict):
                    oid = nested.get("oid")
            if oid is not None:
                protective_oids.append(int(oid))

        if tp_count >= 1 and sl_count >= 1:
            logger.info(
                f"Conferma ordini protettivi ({attempt}/{attempts}): "
                f"TP={tp_count}, SL={sl_count}, oids={sorted(set(protective_oids))}"
            )
            return True, tp_count, sl_count, sorted(set(protective_oids))

        time.sleep(sleep_sec)

    return False, 0, 0, []


def build_atomic_action(
    asset_id: int,
    is_buy: bool,
    size_str: str,
    entry_price_str: str,
    tp_price_str: str,
    sl_price_str: str,
) -> Dict:
    close_is_buy = not is_buy

    entry_order = {
        "a": asset_id,
        "b": is_buy,
        "p": entry_price_str,
        "s": size_str,
        "r": False,
        "t": {"limit": {"tif": "Gtc"}},
    }

    tp_order = {
        "a": asset_id,
        "b": close_is_buy,
        "p": "0",
        "s": size_str,
        "r": True,
        "t": {
            "trigger": {
                "isMarket": True,
                "triggerPx": tp_price_str,
                "tpsl": "tp",
            }
        },
    }

    sl_order = {
        "a": asset_id,
        "b": close_is_buy,
        "p": "0",
        "s": size_str,
        "r": True,
        "t": {
            "trigger": {
                "isMarket": True,
                "triggerPx": sl_price_str,
                "tpsl": "sl",
            }
        },
    }

    return {
        "type": "order",
        "orders": [entry_order, tp_order, sl_order],
        "grouping": "positionTpsl",
    }


def validate_exchange_ack(result: Dict) -> Tuple[bool, str]:
    if not isinstance(result, dict):
        return False, "invalid_response_type"
    if result.get("status") != "ok":
        return False, f"exchange_status_{result.get('status', 'unknown')}"

    statuses = result.get("response", {}).get("data", {}).get("statuses", [])
    if isinstance(statuses, list):
        for st in statuses:
            if isinstance(st, dict) and st.get("error"):
                return False, f"status_error:{st.get('error')}"
        if statuses and not any((isinstance(st, dict) and (st.get("resting") or st.get("filled"))) for st in statuses):
            return False, "not_acknowledged"
    return True, "ok"


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
        raise RuntimeError(
            f"Mismatch key/address: derived={derived} env={env_wallet}. "
            "Correggi .env prima del test."
        )

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
    orders_confirm_attempts = int(os.getenv("TEST_ORDERS_CONFIRM_ATTEMPTS", "15"))
    orders_confirm_sleep_sec = float(os.getenv("TEST_ORDERS_CONFIRM_SLEEP_SEC", "1"))

    if margin_usd <= 0:
        raise RuntimeError("TEST_MARGIN_USD deve essere > 0")
    if leverage < 1:
        raise RuntimeError("TEST_LEVERAGE deve essere >= 1")
    if sl_pct <= 0 or sl_pct >= 1:
        raise RuntimeError("TEST_SL_PCT deve essere tra 0 e 1")
    if tp_pct <= 0 or tp_pct >= 2:
        raise RuntimeError("TEST_TP_PCT deve essere tra 0 e 2")
    if ioc_buffer_pct < 0 or ioc_buffer_pct > Decimal("0.2"):
        raise RuntimeError("TEST_IOC_BUFFER_PCT fuori range ragionevole")
    if min_notional_usd < Decimal("10"):
        raise RuntimeError("TEST_MIN_NOTIONAL_USD deve essere >= 10")

    logger.warning("TEST LIVE REALE ATTIVO: questo script può aprire una posizione con soldi reali")
    logger.info(f"Wallet diagnostics: derived={mask_wallet(derived)} env={mask_wallet(env_wallet)}")
    logger.info(
        f"Parametri: coin={coin}, side={side}, margin={margin_usd}, lev={leverage}, "
        f"sl_pct={sl_pct}, tp_pct={tp_pct}, min_notional={min_notional_usd}"
    )

    client = HyperliquidExchangeClient(
        base_url=base_url,
        private_key=private_key,
        enable_mainnet_trading=enable_mainnet,
        execution_mode=execution_mode,
    )

    trading_user = client.get_trading_user_address()
    if trading_user.lower() != derived.lower():
        raise RuntimeError(
            f"Identità non coerente: signer={derived} trading_user={trading_user}. "
            "Il test richiede signer e trading_user uguali."
        )

    logger.info(
        f"Client diagnostics: signer={client.get_wallet_address_masked()} "
        f"trading_user={mask_wallet(trading_user)} (match signer=yes)"
    )

    mids = client.get_all_mids(force_refresh=True)
    if not isinstance(mids, dict) or coin not in mids:
        raise RuntimeError(f"Mid price non disponibile per {coin}")

    mid_price = Decimal(str(mids[coin]))
    if mid_price <= 0:
        raise RuntimeError(f"Prezzo mid non valido per {coin}: {mid_price}")

    asset_id = client.get_asset_id(coin)
    if asset_id is None:
        raise RuntimeError(f"Asset ID non trovato per {coin}")

    tick_size, step_size, px_decimals, sz_decimals = get_asset_precision_from_meta(client, coin)
    if tick_size <= 0 or step_size <= 0:
        raise RuntimeError(f"Precisione non valida per {coin}: tick={tick_size}, step={step_size}")

    logger.info(
        f"{coin} mid={mid_price} tick={tick_size} step={step_size} "
        f"px_decimals={px_decimals} sz_decimals={sz_decimals}"
    )

    max_leverage = client.get_max_leverage(coin)
    if leverage > max_leverage:
        leverage = max_leverage
        logger.info(f"Leverage ridotta al massimo consentito: {leverage}")

    leverage_ok = client.set_leverage(coin, leverage)
    if not leverage_ok:
        raise RuntimeError(f"Impossibile impostare leverage su {coin}")

    notional_usd = margin_usd * Decimal(str(leverage))
    raw_size = notional_usd / mid_price
    normalized_size = normalize_size_for_min_notional(
        raw_size=raw_size,
        mid_price=mid_price,
        min_notional_usd=min_notional_usd,
        sz_decimals=sz_decimals,
    )
    if normalized_size <= 0:
        raise RuntimeError("Size normalizzata non valida")

    normalized_size = quantize_to_step(normalized_size, step_size, sz_decimals)
    size_str = format_size_for_step(normalized_size, step_size, sz_decimals)

    expected_notional = normalized_size * mid_price
    if expected_notional < Decimal("10"):
        raise RuntimeError(
            f"Notional sotto minimo dopo normalizzazione: {expected_notional} "
            f"(size={normalized_size}, mid={mid_price})"
        )

    size_before_entry = get_position_size(client, trading_user, coin)
    logger.info(f"Posizione prima entry su {coin}: size={size_before_entry}")

    if side == "buy":
        entry_price_raw = mid_price * (Decimal("1") + ioc_buffer_pct)
        entry_price_quantized = quantize_to_tick(entry_price_raw, tick_size, px_decimals)
        sl_price_raw = entry_price_quantized * (Decimal("1") - sl_pct)
        tp_price_raw = entry_price_quantized * (Decimal("1") + tp_pct)
        close_side = "sell"
    else:
        entry_price_raw = mid_price * (Decimal("1") - ioc_buffer_pct)
        entry_price_quantized = quantize_to_tick(entry_price_raw, tick_size, px_decimals)
        sl_price_raw = entry_price_quantized * (Decimal("1") + sl_pct)
        tp_price_raw = entry_price_quantized * (Decimal("1") - tp_pct)
        close_side = "buy"

    entry_price_str = format_price_for_tick(entry_price_quantized, tick_size, px_decimals)
    sl_price_str = format_price_for_tick(sl_price_raw, tick_size, px_decimals)
    tp_price_str = format_price_for_tick(tp_price_raw, tick_size, px_decimals)

    logger.info(
        "Prezzi formattati strict tick (metadata): "
        f"entry={entry_price_str}, sl={sl_price_str}, tp={tp_price_str}, tick={tick_size}"
    )

    action = build_atomic_action(
        asset_id=asset_id,
        is_buy=(side == "buy"),
        size_str=size_str,
        entry_price_str=entry_price_str,
        tp_price_str=tp_price_str,
        sl_price_str=sl_price_str,
    )

    logger.info("Payload batch inviato:\n" + json.dumps(action, indent=2))

    result = client._post_signed_action_with_master_retry(action)
    ok, reason = validate_exchange_ack(result if isinstance(result, dict) else {})
    if not ok:
        raise RuntimeError(f"Batch atomico fallito: {reason} | raw={result}")

    logger.info(f"Batch successo: {result}")

    min_delta = normalized_size * Decimal("0.8")
    entry_confirmed, size_after_entry = wait_position_delta_confirmation(
        client=client,
        trading_user=trading_user,
        coin=coin,
        size_before=size_before_entry,
        side=side,
        min_abs_delta=min_delta,
        attempts=entry_confirm_attempts,
        sleep_sec=entry_confirm_sleep_sec,
    )
    if not entry_confirmed:
        raise RuntimeError(
            f"Entry non confermata entro timeout: before={size_before_entry}, now={size_after_entry}, min_delta={min_delta}"
        )

    protective_ok, tp_count, sl_count, oids = wait_protective_orders_confirmation(
        client=client,
        trading_user=trading_user,
        coin=coin,
        close_side=close_side,
        attempts=orders_confirm_attempts,
        sleep_sec=orders_confirm_sleep_sec,
    )
    if not protective_ok:
        raise RuntimeError("TP/SL non confermati aperti su exchange entro timeout")

    logger.info(
        f"Test completato con successo: entry confermata + protettivi presenti "
        f"(TP={tp_count}, SL={sl_count}, oids={oids})"
    )


if __name__ == "__main__":
    main()