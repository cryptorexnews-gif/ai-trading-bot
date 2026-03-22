#!/usr/bin/env python3
"""
Test live: apertura posizione a mercato con SL/TP in un unico invio (/exchange action bulk).
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
"""

import logging
import os
from decimal import Decimal

from dotenv import load_dotenv

from exchange.market_rules import normalize_size_for_decimals
from exchange_client import HyperliquidExchangeClient
from utils.hyperliquid_state import get_open_positions

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("live_atomic_market_tpsl")


def d(value: str, default: str) -> Decimal:
    raw = os.getenv(value, default)
    return Decimal(str(raw))


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

    coin = os.getenv("TEST_COIN", "ETH").strip().upper()
    side = os.getenv("TEST_SIDE", "buy").strip().lower()
    if side not in {"buy", "sell"}:
        raise RuntimeError("TEST_SIDE invalido: usare 'buy' o 'sell'")

    margin_usd = d("TEST_MARGIN_USD", "2")
    leverage = int(d("TEST_LEVERAGE", "5"))
    sl_pct = d("TEST_SL_PCT", "0.03")
    tp_pct = d("TEST_TP_PCT", "0.06")
    ioc_buffer_pct = d("TEST_IOC_BUFFER_PCT", "0.01")

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

    logger.warning("TEST LIVE REALE ATTIVO: questo script può aprire una posizione con soldi reali")
    logger.info(
        f"Parametri test: coin={coin}, side={side}, margin={margin_usd}, "
        f"leverage={leverage}, sl_pct={sl_pct}, tp_pct={tp_pct}"
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
    if mid_price <= 0:
        raise RuntimeError(f"Prezzo mid non valido per {coin}: {mid_price}")

    logger.info(f"{coin} mid price: {mid_price}")

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
    normalized_size = normalize_size_for_decimals(raw_size, sz_decimals if sz_decimals is not None else -1)
    if normalized_size <= 0:
        raise RuntimeError(f"Size normalizzata non valida: {normalized_size}")

    is_entry_buy = side == "buy"
    if is_entry_buy:
        entry_limit = mid_price * (Decimal("1") + ioc_buffer_pct)
        sl_trigger = mid_price * (Decimal("1") - sl_pct)
        tp_trigger = mid_price * (Decimal("1") + tp_pct)
        close_is_buy = False
    else:
        entry_limit = mid_price * (Decimal("1") - ioc_buffer_pct)
        sl_trigger = mid_price * (Decimal("1") + sl_pct)
        tp_trigger = mid_price * (Decimal("1") - tp_pct)
        close_is_buy = True

    logger.info(
        f"Ordine entry: side={side.upper()} size={normalized_size} limit={entry_limit} "
        f"(notional~{(normalized_size * mid_price):.4f})"
    )
    logger.info(f"Protezioni: SL trigger={sl_trigger}, TP trigger={tp_trigger}")

    orders = [
        {
            "coin": coin,
            "is_buy": is_entry_buy,
            "sz": normalized_size,
            "limit_px": entry_limit,
            "order_type": {"limit": {"tif": "Ioc"}},
            "reduce_only": False,
        },
        {
            "coin": coin,
            "is_buy": close_is_buy,
            "sz": normalized_size,
            "limit_px": sl_trigger,
            "order_type": {"trigger": {"isMarket": True, "triggerPx": sl_trigger, "tpsl": "sl"}},
            "reduce_only": True,
        },
        {
            "coin": coin,
            "is_buy": close_is_buy,
            "sz": normalized_size,
            "limit_px": tp_trigger,
            "order_type": {"trigger": {"isMarket": True, "triggerPx": tp_trigger, "tpsl": "tp"}},
            "reduce_only": True,
        },
    ]

    result = client.bulk_orders(orders, grouping="positionTpsl")
    if not result.get("success"):
        raise RuntimeError(f"Bulk order fallito: {result}")

    logger.info(f"Bulk order inviato con successo. order_ids={result.get('order_ids', [])}")

    user_state = client.get_user_state(wallet)
    if not isinstance(user_state, dict):
        raise RuntimeError("Impossibile leggere user state dopo il test")

    open_positions = get_open_positions(user_state)
    current_pos = open_positions.get(coin)
    if not current_pos:
        logger.warning(
            f"Nessuna posizione aperta su {coin} rilevata subito dopo il test "
            f"(possibile IOC non fillato completamente)."
        )
    else:
        logger.info(
            f"Posizione aperta confermata su {coin}: "
            f"size={current_pos.get('size')} entry={current_pos.get('entry_price')}"
        )

    logger.info("Test completato.")


if __name__ == "__main__":
    main()