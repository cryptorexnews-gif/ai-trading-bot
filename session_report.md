# Hyperliquid Trading Bot - Operations Manual

## Description

Automated trading bot for Hyperliquid exchange powered by **Claude Opus 4.6** via OpenRouter. All market data sourced exclusively from Hyperliquid API. Features multi-timeframe analysis, SL/TP/trailing stop/break-even management, correlation-based risk control, real equity curve tracking, Prometheus metrics, and a real-time React dashboard.

## Project Structure

```
hyperliquid/
├── hyperliquid_bot_executable_orders.py  # Main bot entry point
├── config/
│   ├── __init__.py
│   └── bot_config.py                    # BotConfig dataclass (all env vars)
├── cycle_orchestrator.py                 # Trading cycle phases (health → portfolio → SL/TP → trade)
├── portfolio_service.py                  # Portfolio state fetching from Hyperliquid
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
├── api/
│   ├── __init__.py                       # Flask app factory
│   ├── config.py                         # API configuration constants
│   ├── auth.py                           # API key authentication decorator
│   ├── json_provider.py                  # Custom JSON provider (Decimal → float)
│   ├── helpers.py                        # Shared helpers (file I/O, Hyperliquid proxy, sanitization)
│   └── routes/
│       ├── __init__.py
│       ├── health.py                     # /api/health (no auth)
│       ├── bot.py                        # /api/status, /api/portfolio, /api/config, etc.
│       ├── trading.py                    # /api/trades, /api/performance, /api/trades/export
│       ├── market.py                     # /api/candles, /api/orderbook (Hyperliquid proxy)
│       ├── logs.py                       # /api/logs (sanitized)
│       └── metrics.py                    # /metrics (Prometheus format)
├── api_server.py                         # Thin entry point for API server
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
│   ├── file_io.py                        # Atomic file writes with 0o600 permissions
│   ├── http.py                           # Shared HTTP session factory with retry
│   ├── circuit_breaker.py                # Circuit breaker pattern
│   ├── rate_limiter.py                   # Token bucket rate limiter
│   ├── retry.py                          # HTTP retry with backoff
│   ├── decimals.py                       # Decimal arithmetic utilities
│   ├── validation.py                     # Input validation
│   ├── metrics.py                        # Metrics collection + Prometheus export
│   ├── health.py                         # Health monitoring
│   └── logging_config.py                 # Structured JSON logging
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_risk_manager.py
│   ├── test_technical_indicators.py
│   ├── test_decimals.py
│   └── test_state_store.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── index.css
│       ├── hooks/useApi.js
│       └── components/
│           ├── StatusBadge.jsx
│           ├── StatCard.jsx
│           ├── PositionsTable.jsx
│           ├── ManagedPositions.jsx
│           ├── TradeHistory.jsx
│           ├── EquityChart.jsx
│           ├── PriceChart.jsx            # Real-time candlestick chart
│           ├── OrderBook.jsx             # L2 order book with depth
│           ├── CircuitBreakerStatus.jsx
│           ├── LogViewer.jsx
│           ├── DrawdownBar.jsx
│           ├── ConnectionStatus.jsx
│           ├── ExportButton.jsx
│           └── ErrorBoundary.jsx
└── state/                                # Runtime state (auto-created)
    ├── bot_state.json
    ├── bot_metrics.json
    ├── bot_live_status.json
    └── managed_positions.json
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Dashboard React                       │
│  (Charts, Order Book, Positions, Trades, Logs, BE)      │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (polling every 5s)
┌──────────────────────▼──────────────────────────────────┐
│              API Server (Flask Blueprints)                │
│  api/routes: health, bot, trading, market, logs, metrics │
└──────────────────────┬──────────────────────────────────┘
                       │ Reads shared JSON files
┌──────────────────────▼──────────────────────────────────┐
│              Bot Process                                 │
│                                                           │
│  BotConfig ──→ HyperliquidBot ──→ CycleOrchestrator     │
│                                                           │
│  Phases per cycle:                                        │
│    1. Health check                                        │
│    2. Portfolio snapshot (PortfolioService)               │
│    3. SL/TP/Trailing/Break-even (PositionManager)        │
│    4. Emergency de-risk (RiskManager)                    │
│    5. Correlation analysis (CorrelationEngine)           │
│    6. Per-coin: technicals → LLM → risk → execute       │
│    7. State persistence (StateStore)                     │
└──────────────────────────────────────────────────────────┘
```

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

## Status: PRODUCTION READY
Last Updated: 2025