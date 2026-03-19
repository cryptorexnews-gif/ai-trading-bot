import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from models import (
    ManagedPosition,
    StopLossConfig,
    TakeProfitConfig,
    TrailingStopConfig,
)

logger = logging.getLogger(__name__)

MANAGED_POSITIONS_PATH = "state/managed_positions.json"


class PositionManager:
    """
    Gestisce posizioni con stop-loss, take-profit, e trailing stop.
    Controlla posizioni contro prezzi correnti e attiva chiusure quando necessario.
    Persiste stato posizione gestita su disco.
    """

    def __init__(
        self,
        default_sl_pct: Decimal = Decimal("0.03"),
        default_tp_pct: Decimal = Decimal("0.05"),
        default_trailing_callback: Decimal = Decimal("0.02"),
        enable_trailing_stop: bool = True,
        trailing_activation_pct: Decimal = Decimal("0.02"),
    ):
        self.default_sl_pct = default_sl_pct
        self.default_tp_pct = default_tp_pct
        self.default_trailing_callback = default_trailing_callback
        self.enable_trailing_stop = enable_trailing_stop
        self.trailing_activation_pct = trailing_activation_pct
        self._managed: Dict[str, ManagedPosition] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Carica posizioni gestite da disco."""
        if not os.path.exists(MANAGED_POSITIONS_PATH):
            return
        try:
            with open(MANAGED_POSITIONS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for coin, pos_data in data.items():
                self._managed[coin] = ManagedPosition.from_dict(pos_data)
            logger.info(f"Caricate {len(self._managed)} posizioni gestite da disco")
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning(f"Impossibile caricare posizioni gestite: {e}")

    def _save_state(self) -> None:
        """Persisti posizioni gestite su disco atomicamente."""
        os.makedirs(os.path.dirname(MANAGED_POSITIONS_PATH) or ".", exist_ok=True)
        data = {coin: pos.to_dict() for coin, pos in self._managed.items()}
        tmp_path = MANAGED_POSITIONS_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, MANAGED_POSITIONS_PATH)

    def sync_with_exchange(
        self,
        exchange_positions: Dict[str, Dict[str, Any]]
    ) -> None:
        """
        Sincronizza posizioni gestite con posizioni exchange effettive.
        Rimuove voci gestite per posizioni che non esistono più.
        Aggiunge voci gestite per nuove posizioni trovate su exchange.
        """
        # Rimuovi posizioni gestite che non sono più su exchange
        closed_coins = [
            coin for coin in self._managed
            if coin not in exchange_positions
        ]
        for coin in closed_coins:
            logger.info(f"Posizione {coin} chiusa su exchange, rimuovo da gestite")
            del self._managed[coin]

        # Aggiungi nuove posizioni trovate su exchange che non sono gestite ancora
        for coin, pos in exchange_positions.items():
            size = Decimal(str(pos.get("size", 0)))
            if size == 0:
                continue
            if coin not in self._managed:
                entry_price = Decimal(str(pos.get("entry_price", 0)))
                is_long = size > 0

                # Calcola prezzo attivazione trailing stop
                activation_price = None
                if self.enable_trailing_stop:
                    if is_long:
                        activation_price = entry_price * (Decimal("1") + self.trailing_activation_pct)
                    else:
                        activation_price = entry_price * (Decimal("1") - self.trailing_activation_pct)

                managed = ManagedPosition(
                    coin=coin,
                    size=abs(size),
                    entry_price=entry_price,
                    is_long=is_long,
                    leverage=1,
                    opened_at=time.time(),
                    stop_loss=StopLossConfig(
                        enabled=True,
                        percentage=self.default_sl_pct,
                    ),
                    take_profit=TakeProfitConfig(
                        enabled=True,
                        percentage=self.default_tp_pct,
                    ),
                    trailing_stop=TrailingStopConfig(
                        enabled=self.enable_trailing_stop,
                        callback_rate=self.default_trailing_callback,
                        activation_price=activation_price,
                    ),
                )
                self._managed[coin] = managed
                logger.info(
                    f"Nuova posizione gestita: {coin} {'LONG' if is_long else 'SHORT'} "
                    f"entry=${entry_price} SL={float(self.default_sl_pct)*100}% "
                    f"TP={float(self.default_tp_pct)*100}% "
                    f"trailing={'ON' if self.enable_trailing_stop else 'OFF'}"
                )
            else:
                # Aggiorna dimensione se cambiata (chiusura parziale, aumento, ecc.)
                existing = self._managed[coin]
                new_size = abs(size)
                if new_size != existing.size:
                    existing.size = new_size
                    existing.is_long = size > 0

        self._save_state()

    def check_all_positions(
        self,
        current_prices: Dict[str, Decimal]
    ) -> List[Dict[str, Any]]:
        """
        Controlla tutte le posizioni gestite contro prezzi correnti.
        Ritorna lista di azioni da intraprendere (ordini chiusura).
        """
        actions = []

        for coin, managed in self._managed.items():
            if coin not in current_prices:
                continue

            current_price = current_prices[coin]

            # Controlla trailing stop prima (aggiorna prezzi estremi)
            if managed.should_trailing_stop(current_price):
                ts_price = managed.trailing_stop.get_trailing_stop_price(managed.is_long)
                actions.append({
                    "coin": coin,
                    "trigger": "trailing_stop",
                    "action": "close_position",
                    "size": managed.size,
                    "is_long": managed.is_long,
                    "current_price": current_price,
                    "trigger_price": ts_price,
                    "entry_price": managed.entry_price,
                    "reasoning": (
                        f"Trailing stop attivato per {coin}: "
                        f"prezzo=${current_price} colpito trailing stop a ${ts_price}"
                    )
                })
                continue

            # Aggiorna trailing stop estremi anche se non attivato
            if managed.trailing_stop.enabled:
                managed.trailing_stop.update_extreme(current_price, managed.is_long)

            # Controlla stop-loss
            if managed.should_stop_loss(current_price):
                sl_price = managed.stop_loss.calculate_stop_price(
                    managed.entry_price, managed.is_long
                )
                actions.append({
                    "coin": coin,
                    "trigger": "stop_loss",
                    "action": "close_position",
                    "size": managed.size,
                    "is_long": managed.is_long,
                    "current_price": current_price,
                    "trigger_price": sl_price,
                    "entry_price": managed.entry_price,
                    "reasoning": (
                        f"Stop-loss attivato per {coin}: "
                        f"prezzo=${current_price} violato SL a ${sl_price}"
                    )
                })
                continue

            # Controlla take-profit
            if managed.should_take_profit(current_price):
                tp_price = managed.take_profit.calculate_tp_price(
                    managed.entry_price, managed.is_long
                )
                actions.append({
                    "coin": coin,
                    "trigger": "take_profit",
                    "action": "close_position",
                    "size": managed.size,
                    "is_long": managed.is_long,
                    "current_price": current_price,
                    "trigger_price": tp_price,
                    "entry_price": managed.entry_price,
                    "reasoning": (
                        f"Take-profit attivato per {coin}: "
                        f"prezzo=${current_price} raggiunto TP a ${tp_price}"
                    )
                })

        # Salva estremi trailing stop aggiornati
        self._save_state()
        return actions

    def register_position(
        self,
        coin: str,
        size: Decimal,
        entry_price: Decimal,
        is_long: bool,
        leverage: int = 1,
        sl_pct: Optional[Decimal] = None,
        tp_pct: Optional[Decimal] = None,
        trailing: Optional[bool] = None,
    ) -> None:
        """Registra una nuova posizione con gestione rischio."""
        sl_pct = sl_pct or self.default_sl_pct
        tp_pct = tp_pct or self.default_tp_pct
        use_trailing = trailing if trailing is not None else self.enable_trailing_stop

        activation_price = None
        if use_trailing:
            if is_long:
                activation_price = entry_price * (Decimal("1") + self.trailing_activation_pct)
            else:
                activation_price = entry_price * (Decimal("1") - self.trailing_activation_pct)

        self._managed[coin] = ManagedPosition(
            coin=coin,
            size=abs(size),
            entry_price=entry_price,
            is_long=is_long,
            leverage=leverage,
            opened_at=time.time(),
            stop_loss=StopLossConfig(enabled=True, percentage=sl_pct),
            take_profit=TakeProfitConfig(enabled=True, percentage=tp_pct),
            trailing_stop=TrailingStopConfig(
                enabled=use_trailing,
                callback_rate=self.default_trailing_callback,
                activation_price=activation_price,
            ),
        )
        self._save_state()
        logger.info(
            f"Registrata posizione gestita: {coin} {'LONG' if is_long else 'SHORT'} "
            f"size={size} entry=${entry_price} SL={float(sl_pct)*100}% TP={float(tp_pct)*100}%"
        )

    def remove_position(self, coin: str) -> None:
        """Rimuovi una posizione gestita (dopo chiusura)."""
        if coin in self._managed:
            del self._managed[coin]
            self._save_state()
            logger.info(f"Rimossa posizione gestita: {coin}")

    def get_managed_positions(self) -> Dict[str, ManagedPosition]:
        """Ottieni tutte le posizioni gestite."""
        return self._managed.copy()

    def get_position_status(self) -> List[Dict[str, Any]]:
        """Ottieni stato di tutte le posizioni gestite per dashboard."""
        statuses = []
        for coin, pos in self._managed.items():
            sl_price = pos.stop_loss.calculate_stop_price(pos.entry_price, pos.is_long)
            tp_price = pos.take_profit.calculate_tp_price(pos.entry_price, pos.is_long)
            ts_price = pos.trailing_stop.get_trailing_stop_price(pos.is_long)

            statuses.append({
                "coin": coin,
                "side": "LONG" if pos.is_long else "SHORT",
                "size": str(pos.size),
                "entry_price": str(pos.entry_price),
                "stop_loss_price": str(sl_price),
                "take_profit_price": str(tp_price),
                "trailing_stop_price": str(ts_price) if ts_price else None,
                "trailing_enabled": pos.trailing_stop.enabled,
                "highest_tracked": str(pos.trailing_stop.highest_price) if pos.trailing_stop.highest_price else None,
                "lowest_tracked": str(pos.trailing_stop.lowest_price) if pos.trailing_stop.lowest_price else None,
                "opened_at": pos.opened_at,
            })
        return statuses