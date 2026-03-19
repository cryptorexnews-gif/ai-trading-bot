import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from technical_analyzer_simple import technical_fetcher

logger = logging.getLogger(__name__)


class CorrelationEngine:
    """
    Calcola correlazioni prezzo tra asset usando dati candele Hyperliquid.
    Usato per prevenire aperture posizioni correlate che moltiplicano rischio.
    """

    def __init__(self, correlation_threshold: Decimal = Decimal("0.7")):
        self.correlation_threshold = correlation_threshold
        self._cache: Dict[str, Dict[str, Decimal]] = {}
        self._cache_at: float = 0.0
        self._cache_ttl: float = 600.0  # 10 minuti

    def _calculate_pearson(
        self,
        prices_a: List[Decimal],
        prices_b: List[Decimal]
    ) -> Decimal:
        """Calcola correlazione Pearson tra due serie prezzi usando returns."""
        n = min(len(prices_a), len(prices_b))
        if n < 10:
            return Decimal("0")

        # Calcola returns
        returns_a = []
        returns_b = []
        for i in range(1, n):
            if prices_a[i - 1] != 0 and prices_b[i - 1] != 0:
                returns_a.append((prices_a[i] - prices_a[i - 1]) / prices_a[i - 1])
                returns_b.append((prices_b[i] - prices_b[i - 1]) / prices_b[i - 1])

        if len(returns_a) < 5:
            return Decimal("0")

        n_r = Decimal(str(len(returns_a)))
        mean_a = sum(returns_a) / n_r
        mean_b = sum(returns_b) / n_r

        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(returns_a, returns_b)) / n_r
        var_a = sum((a - mean_a) ** 2 for a in returns_a) / n_r
        var_b = sum((b - mean_b) ** 2 for b in returns_b) / n_r

        if var_a <= 0 or var_b <= 0:
            return Decimal("0")

        std_a = self._sqrt(var_a)
        std_b = self._sqrt(var_b)

        if std_a == 0 or std_b == 0:
            return Decimal("0")

        correlation = cov / (std_a * std_b)
        # Clamp a [-1, 1]
        return max(Decimal("-1"), min(Decimal("1"), correlation))

    def _sqrt(self, value: Decimal) -> Decimal:
        if value <= 0:
            return Decimal("0")
        x = value
        for _ in range(50):
            x = (x + value / x) / Decimal("2")
        return x

    def calculate_correlations(
        self,
        coins: List[str],
        interval: str = "1h",
        limit: int = 50
    ) -> Dict[str, Dict[str, Decimal]]:
        """Calcola correlazioni pairwise per una lista di coin."""
        now = time.time()
        if self._cache and (now - self._cache_at) < self._cache_ttl:
            return self._cache

        # Recupera dati candele per tutte le coin
        candle_data: Dict[str, List[Decimal]] = {}
        for coin in coins:
            candles = technical_fetcher.get_candle_snapshot(coin, interval, limit)
            if candles and len(candles) >= 10:
                candle_data[coin] = [c["close"] for c in candles]

        # Calcola correlazioni pairwise
        correlations: Dict[str, Dict[str, Decimal]] = {}
        coin_list = list(candle_data.keys())

        for i, coin_a in enumerate(coin_list):
            correlations[coin_a] = {}
            for j, coin_b in enumerate(coin_list):
                if i == j:
                    correlations[coin_a][coin_b] = Decimal("1")
                elif j < i and coin_b in correlations and coin_a in correlations[coin_b]:
                    correlations[coin_a][coin_b] = correlations[coin_b][coin_a]
                else:
                    corr = self._calculate_pearson(candle_data[coin_a], candle_data[coin_b])
                    correlations[coin_a][coin_b] = corr

        self._cache = correlations
        self._cache_at = now

        logger.info(f"Matrice correlazione aggiornata per {len(coin_list)} coin")
        return correlations

    def check_correlation_risk(
        self,
        coin: str,
        action: str,
        existing_positions: Dict[str, Dict[str, Any]],
        correlations: Dict[str, Dict[str, Decimal]]
    ) -> Tuple[bool, str]:
        """
        Controlla se aprire una posizione creerebbe rischio correlato eccessivo.
        Ritorna (is_safe, reason).
        """
        if action in ["hold", "close_position", "reduce_position"]:
            return True, "ok"

        if coin not in correlations:
            return True, "no_correlation_data"

        is_new_long = action in ["buy", "increase_position"]

        for existing_coin, pos in existing_positions.items():
            if existing_coin == coin:
                continue

            existing_size = Decimal(str(pos.get("size", 0)))
            if existing_size == 0:
                continue

            existing_is_long = existing_size > 0
            corr = correlations.get(coin, {}).get(existing_coin, Decimal("0"))

            # Alta correlazione positiva + stessa direzione = rischio concentrato
            if abs(corr) >= self.correlation_threshold:
                same_direction = (is_new_long and existing_is_long) or (not is_new_long and not existing_is_long)
                if same_direction and corr > 0:
                    return False, (
                        f"high_correlation_{coin}_{existing_coin}_"
                        f"corr={float(corr):.2f}_same_direction"
                    )
                # Alta correlazione negativa + direzione opposta = anche rischio concentrato
                if not same_direction and corr < -self.correlation_threshold:
                    return False, (
                        f"high_neg_correlation_{coin}_{existing_coin}_"
                        f"corr={float(corr):.2f}_opposite_direction"
                    )

        return True, "ok"

    def get_correlation_summary(self, correlations: Dict[str, Dict[str, Decimal]]) -> Dict[str, Any]:
        """Ottieni riepilogo leggibile delle correlazioni."""
        high_corr_pairs = []
        coins = list(correlations.keys())

        for i, coin_a in enumerate(coins):
            for j, coin_b in enumerate(coins):
                if j <= i:
                    continue
                corr = correlations.get(coin_a, {}).get(coin_b, Decimal("0"))
                if abs(corr) >= Decimal("0.5"):
                    high_corr_pairs.append({
                        "pair": f"{coin_a}/{coin_b}",
                        "correlation": float(corr),
                        "strength": "strong" if abs(corr) >= Decimal("0.7") else "moderate"
                    })

        return {
            "total_pairs": len(coins) * (len(coins) - 1) // 2,
            "high_correlation_pairs": sorted(
                high_corr_pairs,
                key=lambda x: abs(x["correlation"]),
                reverse=True
            )
        }