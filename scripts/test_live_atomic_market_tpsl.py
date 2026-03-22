#!/usr/bin/env python3
"""
Test live sequenziale:
1) apertura posizione (entry)
2) impostazione stop loss (transazione separata)
3) impostazione take profit (transazione separata)

ATTENZIONE: usa soldi reali se ENABLE_MAINNET_TRADING=true.

Configurazione via .env:
- HYPERLIQUID_PRIVATE_KEY
- HYPERLIQUID_WALLET_ADDRESS
- EXECUTION_MODE=live
- ENABLE_MAINNET_TRADING=true

Parametri test (opzionali):
- TEST_COIN=ETH
- TEST_SIDE=buy            # buy (long) o sell (short)
- TEST_MARGIN_USD=2
- TEST_LEVERAGE=5
- TEST_SL_PCT=0.03
- TEST_TP_PCT=0.06
- TEST_IOC_BUFFER_PCT=0.01
- TEST_MIN_NOTIONAL_USD=10.5
- TEST_TICK_SIZE=          # opzionale, es: 0.1 (override manuale)
- TEST_POSITION_WAIT_ATTEMPTS=10
- TEST_POSITION_WAIT_SEC=1
- TEST_CONFIRM_WAIT_SEC=2
- TEST_TRIGGER_CONFIRM_ATTEMPTS=15
- TEST_TRIGGER_CONFIRM_SLEEP_SEC=1
"""

import logging
import os
import sys
import time
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Dict, Optional, Tuple

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
logger = logging.getLogger("live_entry_then_sequential_tpsl")


def d(value: str, default: str) -> Decimal:
    raw = os.getenv(value, default)
    return Decimal(str(raw))


def round_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    if price <= 0:
        return price
    units = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return units * tick_size


def mask_wallet(wallet: str) -> str:
    if not wallet or len(wallet) < 12:
        return "invalid_wallet"
    return f"{wallet[:6]}...{wallet[-4:]}"


def normalize_size_for_min_notional(
    raw_size: Decimal,
    mid_price: Decimal,
    min_notional_usd: Decimal,
    sz_decimals: Optional[int],
) -> Decimal:
    if mid_price <= 0:
        return Decimal("0")

    size = normalize_size_for_decimals(raw_size, sz_decimals if sz_decimals is not None else -1)
    if size <= 0:
        return Decimal("0")

    current_notional = size * mid_price
    if current_notional >= min_notional_usd:
        return size

    required_size = min_notional_usd / mid_price
    size = normalize_size_for_decimals(required_size, sz_decimals if sz_decimals is not None else -1)

    if size * mid_price < min_notional_usd and sz_decimals is not None and sz_decimals >= 0:
        step = Decimal("1").scaleb(-sz_decimals)
        size = size + step

    return size


def fetch_open_position_with_retry(
    client: HyperliquidExchangeClient,
    wallet: str,
    coin: str,
    attempts: int,
    sleep_sec: float,
) -> Optional[Dict]:
    for attempt in range(1, attempts + 1):
        user_state = client.get_user_state(wallet)
        if isinstance(user_state, dict):
            positions = get_open_positions(user_state)
            pos = positions.get(coin)
            if pos:
                size = Decimal(str(pos.get("size", "0")))
                if size != 0:
                    logger.info(
                        f"Posizione rilevata al tentativo {attempt}/{attempts}: "
                        f"size={size}, entry={pos.get('entry_price')}"
                    )
                    return pos
        time.sleep(sleep_sec)
    return None


def wait_order_open_confirmation(
    client: HyperliquidExchangeClient,
    wallet: str,
    coin: str,
    order_id: int,
    attempts: int,
    sleep_sec: float,
) -> bool:
    for attempt in range(1, attempts + 1):
        if client.are_order_ids_open(wallet, coin, [order_id]):
            logger.info(f"Ordine {order_id} confermato aperto su exchange ({attempt}/{attempts})")
            return True
        time.sleep(sleep_sec)

    logger.warning(f"Ordine {order_id} non confermato aperto dopo {attempts} tentativi")
    return False


def place_single_protective_order_with_confirmation(
    client: HyperliquidExchangeClient,
    wallet: str,
    coin: str,
    close_side: str,
    close_size: Decimal,
    trigger_price: Decimal,
    tpsl: str,
    confirm_attempts: int,
    confirm_sleep_sec: float,
) -> Tuple[int, bool]:
    result = client.place_trigger_order(
        coin=coin,
        side=close_side,
        size=close_size,
        trigger_price=trigger_price,
        tpsl=tpsl,
        reduce_only=True,
        is_market=True,
    )

    if not result.get("success"):
        raise RuntimeError(f"Order {tpsl.upper()} fallito: {result}")

    order_id = result.get("order_id")
    if order_id is None:
        raise RuntimeError(f"Order {tpsl.upper()} senza order_id: {result}")

    confirmed = wait_order_open_confirmation(
        client=client,
        wallet=wallet,
        coin=coin,
        order_id=int(order_id),
        attempts=confirm_attempts,
        sleep_sec=confirm_sleep_sec,
    )
    return int(order_id), confirmed


def main() -> None:
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    base_url = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
    execution_mode = os.getenv("EXECUTION_MODE", "live").lower()
    enable_mainnet = os.getenv("ENABLE_MAINNET_TRADING", "false").lower() == "true"

    if not private_key:
        raise RuntimeError("HYPERLIQUID_PRIVATE_KEY mancante")
    if not wallet:
        raise RuntimeError("HYPERLIQUID_WALLET_ADDRESS mancante")
    if execution_mode != "live":
        raise RuntimeError("EXECUTION_MODE deve essere 'live' per questo test")
    if not enable_mainnet:
        raise RuntimeError("ENABLE_MAINNET_TRADING deve essere true per questo test")

    derived = Account.from_key(private_key).address
    if derived.lower() != wallet.lower():
        raise RuntimeError(
            f"Mismatch key/address: derived={derived} env={wallet}. "
            f"Correggi .env prima del test."
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
    tick_override_raw = os.getenv("TEST_TICK_SIZE", "").strip()
    position_wait_attempts = int(os.getenv("TEST_POSITION_WAIT_ATTEMPTS", "10"))
    position_wait_sec = float(os.getenv("TEST_POSITION_WAIT_SEC", "1"))
    confirm_wait_sec = float(os.getenv("TEST_CONFIRM_WAIT_SEC", "2"))
    trigger_confirm_attempts = int(os.getenv("TEST_TRIGGER_CONFIRM_ATTEMPTS", "15"))
    trigger_confirm_sleep_sec = float(os.getenv("TEST_TRIGGER_CONFIRM_SLEEP_SEC", "1"))

    if margin_usd <= 0:
        raise RuntimeError("TEST_MARGIN_USD deve essere > 0")
    if leverage < 1:
        raise RuntimeError("TEST_LEVERAGE deve essere >= 1")
    if sl_pct <= 0 or sl_pct >= 1:
        raise RuntimeError("TEST_SL_PCT deve essere tra 0 e 1")
    if tp_pct <= 0 or tp_pct >= 2:
        raise RuntimeError("TEST_TP_PCT deve essere tra 0 e 2")
    if ioc_buffer_pct < 0 or ioc_buffer_pct > 0.2:
        raise RuntimeError("TEST_IOC_BUFFER_PCT fuori range ragionevole")
    if min_notional_usd < Decimal("10"):
        raise RuntimeError("TEST_MIN_NOTIONAL_USD deve essere >= 10")
    if position_wait_attempts < 1:
        raise RuntimeError("TEST_POSITION_WAIT_ATTEMPTS deve essere >= 1")
    if position_wait_sec <= 0:
        raise RuntimeError("TEST_POSITION_WAIT_SEC deve essere > 0")
    if confirm_wait_sec < 0:
        raise RuntimeError("TEST_CONFIRM_WAIT_SEC deve essere >= 0")
    if trigger_confirm_attempts < 1:
        raise RuntimeError("TEST_TRIGGER_CONFIRM_ATTEMPTS deve essere >= 1")
    if trigger_confirm_sleep_sec <= 0:
        raise RuntimeError("TEST_TRIGGER_CONFIRM_SLEEP_SEC deve essere > 0")

    logger.warning("TEST LIVE REALE ATTIVO: questo script può aprire una posizione con soldi reali")
    logger.info(f"Wallet diagnostics: derived={mask_wallet(derived)} env={mask_wallet(wallet)}")
    logger.info(
        f"Parametri test: coin={coin}, side={side}, margin={margin_usd}, "
        f"leverage={leverage}, sl_pct={sl_pct}, tp_pct={tp_pct}, min_notional={min_notional_usd}"
    )

    client = HyperliquidExchangeClient(
        base_url=base_url,
        private_key=private_key,
        enable_mainnet_trading=enable_mainnet,
        execution_mode=execution_mode,
    )

    logger.info(
        f"Client diagnostics: signer={client.get_wallet_address_masked()} "
        f"trading_user={mask_wallet(client.get_trading_user_address())}"
    )

    mids = client.get_all_mids(force_refresh=True)
    if not isinstance(mids, dict) or coin not in mids:
        raise RuntimeError(f"Mid price non disponibile per {coin}")

    mid_price = Decimal(str(mids[coin]))
    if mid_price <= 0:
        raise RuntimeError(f"Prezzo mid non valido per {coin}: {mid_price}")

    logger.info(f"{coin} mid price: {mid_price}")

    asset_id = client.get_asset_id(coin)
    if asset_id is None:
        raise RuntimeError(f"Asset ID non trovato per {coin}")

    tick_size, precision = client.get_tick_size_and_precision(asset_id)
    if tick_override_raw:
        tick_size = Decimal(tick_override_raw)
        logger.warning(f"Tick size override attivo da env: TEST_TICK_SIZE={tick_size}")

    if tick_size <= 0:
        raise RuntimeError(f"Tick size non valida per {coin}: {tick_size}")

    logger.info(f"{coin} tick_size={tick_size} precision={precision}")

    max_leverage = client.get_max_leverage(coin)
    if leverage > max_leverage:
        leverage = max_leverage
        logger.info(f"Leverage ridotta al massimo consentito per {coin}: {leverage}")

    leverage_ok = client.set_leverage(coin, leverage)
    if not leverage_ok:
        raise RuntimeError(f"Impossibile impostare leverage su {coin}")

    notional_usd = margin_usd * Decimal(str(leverage))
    raw_size = notional_usd / mid_price
    sz_decimals = client.get_sz_decimals(coin)
    normalized_size = normalize_size_for_min_notional(
        raw_size=raw_size,
        mid_price=mid_price,
        min_notional_usd=min_notional_usd,
        sz_decimals=sz_decimals,
    )
    if normalized_size <= 0:
        raise RuntimeError(f"Size normalizzata non valida: {normalized_size}")

    expected_notional = normalized_size * mid_price
    if expected_notional < Decimal("10"):
        raise RuntimeError(
            f"Notional ancora sotto minimo dopo normalizzazione: {expected_notional} "
            f"(size={normalized_size}, mid={mid_price})"
        )

    is_entry_buy = side == "buy"
    if is_entry_buy:
        entry_limit = mid_price * (Decimal("1") + ioc_buffer_pct)
    else:
        entry_limit = mid_price * (Decimal("1") - ioc_buffer_pct)

    entry_limit = round_to_tick(entry_limit, tick_size)
    if entry_limit <= 0:
        raise RuntimeError("Prezzo entry arrotondato non valido")

    logger.info(
        f"STEP 1/3 ENTRY: side={side.upper()} size={normalized_size} desired_limit={entry_limit} "
        f"(notional@mid~{expected_notional:.4f})"
    )

    entry_result = client.place_order(
        coin=coin,
        side=side,
        size=normalized_size,
        desired_price=entry_limit,
        reduce_only=False,
    )
    if not entry_result.get("success"):
        raise RuntimeError(f"Entry order fallito: {entry_result}")

    logger.info(f"Entry order successo: {entry_result}")

    pos = fetch_open_position_with_retry(
        client=client,
        wallet=wallet,
        coin=coin,
        attempts=position_wait_attempts,
        sleep_sec=position_wait_sec,
    )

    if not pos:
        raise RuntimeError(
            f"Nessuna posizione aperta visibile su {coin} dopo entry; impossibile continuare con SL/TP."
        )

    pos_size = Decimal(str(pos.get("size", "0")))
    is_long = pos_size > 0
    close_side = "sell" if is_long else "buy"
    close_size = abs(pos_size)

    entry_price = Decimal(str(pos.get("entry_price", "0")))
    if entry_price <= 0:
        fallback_price = Decimal(str(entry_result.get("filled_price", mid_price)))
        entry_price = fallback_price if fallback_price > 0 else mid_price

    if is_long:
        sl_trigger = entry_price * (Decimal("1") - sl_pct)
        tp_trigger = entry_price * (Decimal("1") + tp_pct)
    else:
        sl_trigger = entry_price * (Decimal("1") + sl_pct)
        tp_trigger = entry_price * (Decimal("1") - tp_pct)

    sl_trigger = round_to_tick(sl_trigger, tick_size)
    tp_trigger = round_to_tick(tp_trigger, tick_size)

    if sl_trigger <= 0 or tp_trigger <= 0:
        raise RuntimeError("Trigger SL/TP arrotondati non validi")

    logger.info(
        f"Posizione attuale: size={pos_size} entry={entry_price} "
        f"close_side={close_side} close_size={close_size}"
    )

    if confirm_wait_sec > 0:
        logger.info(f"Attesa conferma post-entry: {confirm_wait_sec}s")
        time.sleep(confirm_wait_sec)

    logger.info(f"STEP 2/3 STOP LOSS: trigger={sl_trigger}")
    sl_id, sl_confirmed = place_single_protective_order_with_confirmation(
        client=client,
        wallet=wallet,
        coin=coin,
        close_side=close_side,
        close_size=close_size,
        trigger_price=sl_trigger,
        tpsl="sl",
        confirm_attempts=trigger_confirm_attempts,
        confirm_sleep_sec=trigger_confirm_sleep_sec,
    )
    logger.info(f"Stop loss creato: oid={sl_id}, confirmed={sl_confirmed}")

    if confirm_wait_sec > 0:
        logger.info(f"Attesa conferma post-SL: {confirm_wait_sec}s")
        time.sleep(confirm_wait_sec)

    logger.info(f"STEP 3/3 TAKE PROFIT: trigger={tp_trigger}")
    tp_id, tp_confirmed = place_single_protective_order_with_confirmation(
        client=client,
        wallet=wallet,
        coin=coin,
        close_side=close_side,
        close_size=close_size,
        trigger_price=tp_trigger,
        tpsl="tp",
        confirm_attempts=trigger_confirm_attempts,
        confirm_sleep_sec=trigger_confirm_sleep_sec,
    )
    logger.info(f"Take profit creato: oid={tp_id}, confirmed={tp_confirmed}")

    both_open = client.are_order_ids_open(wallet, coin, [sl_id, tp_id])
    logger.info(f"Verifica finale ordini protettivi aperti (SL+TP): {both_open}")

    if not both_open:
        raise RuntimeError("SL/TP non risultano entrambi aperti su exchange dopo conferma")

    logger.info("Test completato: flusso 3-step sequenziale riuscito (entry -> SL -> TP).")


if __name__ == "__main__":
    main()