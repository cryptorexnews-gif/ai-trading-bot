"""
Test unitari per technical_analyzer_simple.py — indicatori tecnici.
"""

from decimal import Decimal

from technical_analyzer_simple import HyperliquidDataFetcher


def _fetcher() -> HyperliquidDataFetcher:
    return HyperliquidDataFetcher()


# ─── EMA ──────────────────────────────────────────────────────────────────────

def test_ema_basic():
    f = _fetcher()
    prices = [Decimal(str(i)) for i in range(1, 21)]  # 1 to 20
    ema = f.calculate_ema(prices, 5)
    assert len(ema) == len(prices)
    # EMA should be close to recent prices
    assert ema[-1] > Decimal("15"), f"EMA should be > 15, got {ema[-1]}"


def test_ema_insufficient_data():
    f = _fetcher()
    prices = [Decimal("100"), Decimal("101")]
    ema = f.calculate_ema(prices, 5)
    assert all(v == Decimal("0") for v in ema), "Should return zeros for insufficient data"


def test_ema_constant_prices():
    f = _fetcher()
    prices = [Decimal("100")] * 20
    ema = f.calculate_ema(prices, 5)
    # EMA of constant series should be the constant
    assert ema[-1] == Decimal("100"), f"EMA of constant should be 100, got {ema[-1]}"


# ─── RSI (Wilder's) ──────────────────────────────────────────────────────────

def test_rsi_all_gains():
    f = _fetcher()
    # Monotonically increasing prices — RSI should be 100
    prices = [Decimal(str(100 + i)) for i in range(20)]
    rsi = f.calculate_rsi(prices, 14)
    assert rsi[-1] == Decimal("100"), f"RSI of all gains should be 100, got {rsi[-1]}"


def test_rsi_all_losses():
    f = _fetcher()
    # Monotonically decreasing prices — RSI should be 0
    prices = [Decimal(str(120 - i)) for i in range(20)]
    rsi = f.calculate_rsi(prices, 14)
    assert rsi[-1] == Decimal("0"), f"RSI of all losses should be 0, got {rsi[-1]}"


def test_rsi_range():
    f = _fetcher()
    # Mixed prices — RSI should be between 0 and 100
    prices = [Decimal(str(v)) for v in [100, 102, 101, 103, 99, 104, 98, 105, 97, 106, 100, 103, 101, 104, 99, 102]]
    rsi = f.calculate_rsi(prices, 14)
    last_rsi = rsi[-1]
    assert Decimal("0") <= last_rsi <= Decimal("100"), f"RSI should be 0-100, got {last_rsi}"


def test_rsi_insufficient_data():
    f = _fetcher()
    prices = [Decimal("100")] * 5
    rsi = f.calculate_rsi(prices, 14)
    assert all(v == Decimal("50") for v in rsi), "Should return 50 for insufficient data"


def test_rsi_wilder_smoothing():
    """Verify RSI uses Wilder's smoothing (not SMA window)."""
    f = _fetcher()
    # Create a specific price series where Wilder's and SMA RSI would differ
    prices = []
    base = Decimal("100")
    for i in range(30):
        if i < 15:
            base += Decimal("1")  # Uptrend
        else:
            base -= Decimal("0.5")  # Mild downtrend
        prices.append(base)

    rsi = f.calculate_rsi(prices, 14)
    last_rsi = rsi[-1]
    # In a mild downtrend after uptrend, Wilder's RSI should still be > 50
    # because Wilder's smoothing gives more weight to recent history
    assert last_rsi > Decimal("30"), f"Wilder's RSI should be > 30 in mild downtrend, got {last_rsi}"
    assert last_rsi < Decimal("80"), f"Wilder's RSI should be < 80 in mild downtrend, got {last_rsi}"


# ─── MACD ─────────────────────────────────────────────────────────────────────

def test_macd_basic():
    f = _fetcher()
    prices = [Decimal(str(100 + i * 0.5)) for i in range(30)]
    macd_line, signal_line, histogram = f.calculate_macd(prices)
    assert len(macd_line) == len(prices)
    assert len(signal_line) == len(prices)
    assert len(histogram) == len(prices)
    # In uptrend, MACD should be positive
    assert macd_line[-1] > Decimal("0"), f"MACD should be positive in uptrend, got {macd_line[-1]}"


# ─── Bollinger Bands ──────────────────────────────────────────────────────────

def test_bollinger_bands_basic():
    f = _fetcher()
    prices = [Decimal(str(100 + (i % 5) - 2)) for i in range(25)]
    bb = f._calculate_bollinger_bands(prices, 20)
    assert len(bb["upper"]) == len(prices)
    assert len(bb["middle"]) == len(prices)
    assert len(bb["lower"]) == len(prices)
    # Upper > Middle > Lower
    assert bb["upper"][-1] > bb["middle"][-1], "Upper should be > Middle"
    assert bb["middle"][-1] > bb["lower"][-1], "Middle should be > Lower"


def test_bollinger_bands_insufficient_data():
    f = _fetcher()
    prices = [Decimal("100")] * 5
    bb = f._calculate_bollinger_bands(prices, 20)
    assert all(v == Decimal("0") for v in bb["upper"]), "Should return zeros for insufficient data"


# ─── VWAP ─────────────────────────────────────────────────────────────────────

def test_vwap_basic():
    f = _fetcher()
    highs = [Decimal("105"), Decimal("106"), Decimal("107")]
    lows = [Decimal("95"), Decimal("96"), Decimal("97")]
    closes = [Decimal("100"), Decimal("101"), Decimal("102")]
    volumes = [Decimal("1000"), Decimal("2000"), Decimal("3000")]
    vwap = f._calculate_vwap(highs, lows, closes, volumes)
    assert vwap > Decimal("0"), f"VWAP should be positive, got {vwap}"
    # VWAP should be weighted toward higher-volume candles
    assert vwap > Decimal("99"), f"VWAP should be > 99, got {vwap}"


def test_vwap_zero_volume():
    f = _fetcher()
    highs = [Decimal("105")]
    lows = [Decimal("95")]
    closes = [Decimal("100")]
    volumes = [Decimal("0")]
    vwap = f._calculate_vwap(highs, lows, closes, volumes)
    assert vwap == Decimal("100"), f"VWAP with zero volume should return last close"


if __name__ == "__main__":
    import sys
    test_functions = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for test_fn in test_functions:
        try:
            test_fn()
            passed += 1
            print(f"  ✅ {test_fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {test_fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  💥 {test_fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(1 if failed > 0 else 0)