import logging
import time
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class OrderVerifier:
    """
    Verifica che ordini piazzati su Hyperliquid siano stati effettivamente riempiti.
    Confronta stato posizione prima e dopo piazzamento ordine.
    """

    def __init__(self, exchange_client, max_wait_sec: float = 10.0, check_interval: float = 2.0):
        self.exchange_client = exchange_client
        self.max_wait_sec = max_wait_sec
        self.check_interval = check_interval

    def _get_position_size(self, wallet: str, coin: str) -> Decimal:
        """Ottieni dimensione posizione corrente per una coin."""
        user_state = self.exchange_client.get_user_state(wallet)
        if not user_state:
            return Decimal("0")

        for pos in user_state.get("assetPositions", []):
            pos_data = pos.get("position", {})
            if pos_data.get("coin") == coin:
                return Decimal(str(pos_data.get("szi", 0)))
        return Decimal("0")

    def snapshot_position(self, wallet: str, coin: str) -> Dict[str, Any]:
        """Prendi snapshot di stato posizione corrente prima ordine."""
        size = self._get_position_size(wallet, coin)
        return {
            "coin": coin,
            "size_before": size,
            "timestamp": time.time()
        }

    def verify_fill(
        self,
        wallet: str,
        coin: str,
        expected_side: str,
        expected_size: Decimal,
        snapshot: Dict[str, Any<dyad-write path="order_verifier.py">
        tolerance_pct: Decimal = Decimal("0.05")
    ) -> Dict[str, Any]:
        """
        Verifica che un ordine sia stato riempito controllando cambiamento posizione.

        Ritorna dict con:
          - verified: bool
          - fill_status: 'filled', 'partially_filled', 'not_filled', 'unknown'
          - actual_size_change: Decimal
          - expected_size_change: Decimal
        """
        size_before = snapshot.get("size_before", Decimal("0"))
        start_time = time.time()

        # Cambiamento dimensione attesa
        if expected_side == "buy":
            expected_change = expected_size
        else:
            expected_change = -expected_size

        # Poll per riempimento
        while (time.time() - start_time) < self.max_wait_sec:
            current_size = self._get_position_size(wallet, coin)
            actual_change = current_size - size_before

            # Controlla se riempito completamente (entro tolleranza)
            if abs(actual_change) > 0:
                fill_ratio = abs(actual_change) / abs(expected_change) if expected_change != 0 else Decimal("0")

                if fill_ratio >= (Decimal("1") - tolerance_pct):
                    logger.info(
                        f"Ordine verificato RIEMPITO per {coin}: "
                        f"atteso={expected_change}, attuale={actual_change}, "
                        f"fill_ratio={float(fill_ratio)*100:.1f}%"
                    )
                    return {
                        "verified": True,
                        "fill_status": "filled",
                        "actual_size_change": actual_change,
                        "expected_size_change": expected_change,
                        "fill_ratio": fill_ratio,
                        "wait_time": time.time() - start_time
                    }
                elif fill_ratio >= Decimal("0.1"):
                    logger.warning(
                        f"Ordine PARZIALMENTE RIEMPITO per {coin}: "
                        f"atteso={expected_change}, attuale={actual_change}, "
                        f"fill_ratio={float(fill_ratio)*100:.1f}%"
                    )
                    return {
                        "verified": True,
                        "fill_status": "partially_filled",
                        "actual_size_change": actual_change,
                        "expected_size_change": expected_change,
                        "fill_ratio": fill_ratio,
                        "wait_time": time.time() - start_time
                    }

            time.sleep(self.check_interval)

        # Timeout — controlla un'ultima volta
        final_size = self._get_position_size(wallet, coin)
        final_change = final_size - size_before

        if abs(final_change) > 0:
            fill_ratio = abs(final_change) / abs(expected_change) if expected_change != 0 else Decimal("0")
            status = "filled" if fill_ratio >= (Decimal("1") - tolerance_pct) else "partially_filled"
            logger.info(f"Ordine {status} per {coin} (rilevato al timeout): fill_ratio={float(fill_ratio)*100:.1f}%")
            return {
                "verified": True,
                "fill_status": status,
                "actual_size_change": final_change,
                "expected_size_change": expected_change,
                "fill_ratio": fill_ratio,
                "wait_time": self.max_wait_sec
            }

        logger.warning(f"Ordine NON RIEMPITO per {coin} dopo {self.max_wait_sec}s attesa")
        return {
            "verified": False,
            "fill_status": "not_filled",
            "actual_size_change": Decimal("0"),
            "expected_size_change": expected_change,
            "fill_ratio": Decimal("0"),
            "wait_time": self.max_wait_sec
        }