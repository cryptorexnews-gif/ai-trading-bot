# Hyperliquid Trading Bot - Operations Manual

## Description

Automated trading bot for Hyperliquid exchange powered by **Claude Opus 4.6** via OpenRouter. All market data sourced exclusively from Hyperliquid API. Features multi-timeframe analysis, SL/TP/trailing stop management, correlation-based risk control, and a real-time React dashboard.

## Project Structure

```
hyperliquid/
├── hyperliquid_bot_executable_orders.py  # Main bot entry point
├── exchange_client.py                    # Hyperliquid API client (EIP-712 signing)
├── llm_engine.py                         # Claude Opus 4.6 via OpenRouter
├── execution_engine.py                   # Order execution logic
├── risk_manager.py                       # Risk validation (drawdown, margin, sizing)
├── position_manager.py                   # SL/TP/trailing stop management
├── correlation_engine.py                 # Asset correlation analysis
├── technical_analyzer_simple.py          # Technical indicators from HL candles
├── order_verifier.py                     # Post-trade fill verification
├── state_store.py                        # Persistent state (atomic writes)
├── bot_live_writer.py                    # Live status for dashboard
├── notifier.py                           # Telegram notifications
├── models.py                             # Data models (dataclass/enum)
├── api_server.py                         # Flask API for dashboard
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
│   ├── rate_limiter.py                   # Token bucket rate limiter
│   ├── retry.py                          # HTTP retry with backoff
│   ├── decimals.py                       # Decimal arithmetic utilities
│   ├── validation.py                     # Input validation
│   ├── metrics.py                        # Metrics collection
│   ├── health.py                         # Health monitoring
│   └── logging_config.py                 # Structured JSON logging
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
│           ├── CircuitBreakerStatus.jsx
│           ├── LogViewer.jsx
│           ├── DrawdownBar.jsx
│           ├── ConnectionStatus.jsx
│           └── ExportButton.jsx
└── state/                                # Runtime state (auto-created)
    ├── bot_state.json
    ├── bot_metrics.json
    ├── bot_live_status.json
    └── managed_positions.json
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