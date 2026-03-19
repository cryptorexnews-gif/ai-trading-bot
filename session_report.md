# Hyperliquid Trading Bot - Operations Manual

## Description

Automated trading bot for Hyperliquid exchange powered by **Claude Opus 4.6** via OpenRouter. All market data sourced exclusively from Hyperliquid API. Features multi-timeframe analysis, SL/TP/trailing stop/break-even management, correlation-based risk control, real equity curve tracking, Prometheus metrics, and a real-time React dashboard.

## Project Structure

```
hyperliquid/
├── hyperliquid_bot_executable_orders.py  # Main bot entry point
├── exchange_client.py                    # Hyperliquid API client (EIP-712 signing)
├── llm_engine.py                         # Claude Opus 4.6 via OpenRouter (with retry)
├── execution_engine.py                   # Order execution logic
├── risk_manager.py                       # Risk validation (drawdown, margin, sizing)
├── position_manager.py                   # SL/TP/trailing stop/break-even management
├── correlation_engine.py                 # Asset correlation analysis
├── technical_analyzer_simple.py          # Technical indicators (Wilder's RSI, EMA, MACD, BB, VWAP)
├── order_verifier.py                     # Post-trade fill verification
├── state_store.py                        # Persistent state (atomic writes, equity snapshots)
├── bot_live_writer.py                    # Live status for dashboard
├── notifier.py                           # Telegram notifications
├── models.py                             # Data models (dataclass/enum, break-even config)
├── api_server.py                         # Flask API for dashboard + Prometheus /metrics
├── check_current_positions.py            # Position checker utility
├── close_sol_position.py                 # SOL position closer utility
├── hyperliquid_minimal_order.py          # Minimal order test utility
├── requirements.txt                      # Python dependencies
├── .env.example                          # Environment variable template
├── .gitignore                            # Git ignore rules
├── AI_RULES.md                           # AI editor rules
├── README.md                             # Project documentation
├── utils/
│   ├── __init__.py
│   ├── circuit_breaker.py                # Circuit breaker pattern
│   ├── rate_limiter.py                   # Token bucket rate limiter (active)
│   ├── retry.py                          # HTTP retry with backoff (used by LLM)
│   ├── decimals.py                       # Decimal arithmetic utilities + safe_decimal
│   ├── validation.py                     # Input validation
│   ├── metrics.py                        # Metrics collection + Prometheus export
│   ├── health.py                         # Health monitoring (active in bot)
│   └── logging_config.py                 # Structured JSON logging
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx                      # Entry point with ErrorBoundary
│       ├── App.jsx
│       ├── index.css
│       ├── hooks/useApi.js
│       └── components/
│           ├── StatusBadge.jsx
│           ├── StatCard.jsx
│           ├── PositionsTable.jsx
│           ├── ManagedPositions.jsx       # Shows SL/TP/trailing/break-even status
│           ├── TradeHistory.jsx
│           ├── EquityChart.jsx            # Real equity curve from snapshots
│           ├── CircuitBreakerStatus.jsx
│           ├── LogViewer.jsx
│           ├── DrawdownBar.jsx
│           ├── ConnectionStatus.jsx
│           ├── ExportButton.jsx
│           └── ErrorBoundary.jsx          # React error boundary
└── state/                                # Runtime state (auto-created)
    ├── bot_state.json                    # Includes equity_snapshots[]
    ├── bot_metrics.json
    ├── bot_live_status.json
    └── managed_positions.json
```

## Key Improvements Applied

### Code Quality
- **Unified `safe_decimal`**: All files use `utils/decimals.safe_decimal` — no more duplicated `_safe_decimal` methods
- **Centralized `decimal_sqrt`**: 20 Newton-Raphson iterations (was 50), used everywhere
- **`utils/retry.py` integrated**: LLM engine uses `retry_request()` with exponential backoff + jitter
- **No global mutations**: `TRADING_PAIRS` is now instance attribute `self._trading_pairs`

### Trading Logic
- **RSI with Wilder's smoothing**: Standard RSI calculation matching TradingView
- **Tick size from `szDecimals`**: Uses Hyperliquid meta field as primary source (was inferring from mid price)
- **Break-even stop**: Moves SL to entry + 0.1% after +1.5% profit (configurable)
- **Multi-timeframe analysis**: 5m (intraday) + 1h (medium) + 4h (long-term) with alignment detection

### Risk Management
- **Rate limiter active**: Token bucket for Hyperliquid API (20 tokens, 2/s) and OpenRouter (5 tokens, 0.5/s)
- **Health monitor active**: Checks exchange connectivity, disk space, state writability every 10 cycles
- **Configuration validation**: Critical env vars validated at startup with warnings
- **Correlation engine**: Prevents opening correlated positions in same direction

### Observability
- **Prometheus `/metrics` endpoint**: Counters, gauges, circuit breaker states in text format
- **Real equity curve**: Portfolio value snapshots every cycle (last 500 points)
- **Structured JSON logging**: File + console with configurable level
- **React ErrorBoundary**: Catches component crashes with recovery UI

### Dashboard
- **Break-even indicator**: Shows BE activation status on managed positions
- **Real equity chart**: AreaChart from portfolio snapshots (not just trade activity)
- **Export CSV**: Download trade history as CSV file

## Quick Start

1. Copy `.env.example` to `.env` and fill in your keys
2. `pip install -r requirements.txt`
3. `python hyperliquid_bot_executable_orders.py --single-cycle` (test)
4. `python hyperliquid_bot_executable_orders.py` (production)

## Dashboard

```bash
# Terminal 1: API server
python api_server.py

# Terminal 2: Frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:3000

## Prometheus Integration

Metrics available at `http://localhost:5000/metrics` in Prometheus text format.

Example Grafana queries:
- `bot_balance_usd` — Current balance
- `rate(bot_trades_executed_total[1h])` — Trades per hour
- `bot_margin_usage_ratio` — Current margin usage
- `bot_circuit_breaker_hyperliquid_info_state` — Circuit breaker state

## Status: PRODUCTION READY
Last Updated: 2025