# Hyperliquid Trading Bot

An automated cryptocurrency trading bot for the Hyperliquid exchange, powered by **Claude Opus 4.6** via OpenRouter for intelligent trading decisions. All market data is sourced **exclusively from Hyperliquid API** — no external data providers.

## 🚀 Features

### ✅ Core Functionality
- **AI-Powered Trading**: Claude Opus 4.6 (`anthropic/claude-opus-4.6`) via OpenRouter analyzes market data and generates executable trading decisions
- **Hyperliquid-Only Data**: All market data (candles, mid prices, funding rates, open interest) sourced directly from Hyperliquid API
- **Technical Analysis**: EMA, MACD, RSI, ATR, Bollinger Bands, VWAP calculated from Hyperliquid candle snapshots
- **Risk Management**: Volatility-adjusted sizing, margin limits, trade cooldowns, daily notional caps, max drawdown protection
- **Secure Execution**: EIP-712 signed orders via `eth_account` for Hyperliquid mainnet
- **Paper Trading Mode**: Safe testing with simulated executions and slippage
- **Circuit Breakers**: Automatic failure handling for API endpoints
- **Real-Time Dashboard**: React frontend with live portfolio, positions, trade history, and logs
- **Structured Logging**: JSON-formatted logs for monitoring and debugging

### 📊 Dashboard
The bot includes a **real-time web dashboard** built with React + Tailwind CSS:
- 💰 Live portfolio balance and PnL
- 📈 Activity timeline chart
- 📊 Open positions with entry prices and unrealized PnL
- 📋 Full trade history with AI reasoning
- 🛡️ Circuit breaker status
- 📝 Real-time log viewer
- ⚠️ Risk alerts (consecutive losses, failed cycles)

### 📊 Supported Assets
| Asset | Minimum Size | Approx. Value |
|-------|-------------|---------------|
| BTC   | 0.001       | ~$111         |
| ETH   | 0.001       | ~$4           |
| SOL   | 0.1         | ~$19          |
| BNB   | 0.001       | ~$1           |
| ADA   | 16.0        | ~$10.50       |

### 🛡️ Safety Features
- **Max Drawdown Protection**: Stops opening new positions if drawdown exceeds 15%
- **Emergency De-Risk**: Auto-closes worst position if margin usage > 90%
- **Position Conflict Detection**: Prevents opening opposite direction on same asset
- **Per-Asset Concentration Limit**: Max 40% of balance on a single asset
- **Fail-Safe Fallback**: Automatic hold/de-risk when AI is unavailable
- **Circuit Breakers**: Prevents cascading failures from API outages
- **Graceful Shutdown**: SIGINT/SIGTERM handlers save state before exit

## 📋 Requirements

- Python 3.10+
- Node.js 18+ (for dashboard)
- Valid Hyperliquid wallet with private key
- OpenRouter API key (for Claude Opus 4.6 access)

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd hyperliquid-trading-bot
   ```

2. **Install Python dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Install Dashboard dependencies**:
   ```bash
   cd frontend
   npm install
   cd ..
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

## 🚀 Usage

### Start the Bot
```bash
# Single cycle test
python hyperliquid_bot_executable_orders.py --single-cycle

# Continuous trading
python hyperliquid_bot_executable_orders.py
```

### Start the Dashboard
```bash
# Terminal 1: Start API server
python api_server.py

# Terminal 2: Start frontend
cd frontend
npm run dev
```

Then open **http://localhost:3000** in your browser.

### Start Everything Together
```bash
# Terminal 1: Bot
python hyperliquid_bot_executable_orders.py

# Terminal 2: API + Dashboard
python api_server.py &
cd frontend && npm run dev
```

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# === REQUIRED ===
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# === Execution Mode ===
EXECUTION_MODE=paper
ENABLE_MAINNET_TRADING=false

# === AI / LLM Settings ===
LLM_MODEL=anthropic/claude-opus-4.6
LLM_MAX_TOKENS=8192
LLM_TEMPERATURE=0.2

# === Risk Management ===
MAX_ORDER_MARGIN_PCT=0.1
HARD_MAX_LEVERAGE=10
MAX_MARGIN_USAGE=0.8
MAX_DRAWDOWN_PCT=0.15
TRADE_COOLDOWN_SEC=300
DAILY_NOTIONAL_LIMIT_USD=1000

# === API Server ===
API_SERVER_PORT=5000
```

## 🔄 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Dashboard                       │
│  (Portfolio, Positions, Trades, Logs, Circuit Breakers)  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (polling every 5s)
┌──────────────────────▼──────────────────────────────────┐
│                  Flask API Server                         │
│  /api/status  /api/portfolio  /api/trades  /api/logs     │
└──────────────────────┬──────────────────────────────────┘
                       │ Reads shared JSON files
┌──────────────────────▼──────────────────────────────────┐
│              Main Trading Bot Process                     │
│                                                           │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐              │
│  │Exchange  │  │ LLM      │  │ Risk       │              │
│  │Client    │  │ Engine   │  │ Manager    │              │
│  │(HL API)  │  │(Claude)  │  │            │              │
│  └────┬─────┘  └────┬─────┘  └─────┬──────┘              │
│       │              │              │                     │
│  ┌────▼──────────────▼──────────────▼──────┐             │
│  │         Execution Engine                 │             │
│  └────────────────┬────────────────────────┘             │
│                   │                                       │
│  ┌────────────────▼────────────────────────┐             │
│  │    State Store (JSON) + Live Writer      │             │
│  └──────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────┘
```

## ⚠️ Disclaimer

This software is provided as-is without warranty. Cryptocurrency trading is highly risky and can result in total loss of funds. Always test thoroughly in paper mode and never risk more than you can afford to lose.