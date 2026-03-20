# 🤖 Hyperliquid Trading Bot

**AI-Powered Trading Bot for Hyperliquid Exchange**  
*Powered by Claude Opus 4.6 via OpenRouter • All data from Hyperliquid API • Real-time React Dashboard*

[![Dashboard Preview](frontend/src/assets/dashboard-reference.jpg)](frontend/src/assets/dashboard-reference.jpg)

## 🚀 Features

- **AI Decisions**: Claude Opus 4.6 analyzes multi-timeframe technicals (EMA, RSI, MACD, Bollinger Bands, VWAP, ATR)
- **Risk Management**: SL/TP/Trailing Stops/Break-Even • Drawdown protection • Correlation checks • Daily notional caps
- **Live Dashboard**: Real-time equity curve, positions, trades, logs, circuit breakers, order book, candlesticks
- **Production Ready**: Circuit breakers, rate limiting, atomic state persistence, Prometheus metrics, Telegram alerts
- **Paper & Live Trading**: Seamless switch via `EXECUTION_MODE`
- **Hyperliquid Native**: EIP-712 signing, L2 order book, funding rates, open interest

## 📋 Quick Start (5 minutes)

### 1. Prerequisites
```bash
# Python 3.10+
pip install -r requirements.txt

# Node.js 18+
cd frontend && npm install
```

### 2. Setup Environment
```bash
cp .env.example .env
# Edit .env: Add HYPERLIQUID_PRIVATE_KEY, HYPERLIQUID_WALLET_ADDRESS, OPENROUTER_API_KEY
```

### 3. Test Configuration
```bash
python scripts/test_connection.py
```
✅ All tests green? Proceed!

### 4. Test Single Cycle (Paper Mode)
```bash
python hyperliquid_bot_executable_orders.py --single-cycle
```
✅ No errors? Bot is ready!

### 5. Run Bot (Background)
**Terminal 1:**
```bash
python hyperliquid_bot_executable_orders.py
```

**Terminal 2 (API Server):**
```bash
python api_server.py
```

**Terminal 3 (Dashboard):**
```bash
cd frontend && npm run dev
```

✅ Open [http://localhost:3000](http://localhost:3000) — Dashboard live!

## ⚙️ Full Setup Guide

### Step 1: Clone & Install
```bash
git clone <your-repo> hyperliquid-bot
cd hyperliquid-bot
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### Step 2: Environment (.env)
Copy `.env.example` → `.env` and **fill required fields**:

```env
# Hyperliquid (REQUIRED)
HYPERLIQUID_WALLET_ADDRESS=0xYourWalletAddress
HYPERLIQUID_PRIVATE_KEY=0xYourPrivateKey

# OpenRouter LLM (REQUIRED for AI)
OPENROUTER_API_KEY=sk-or-...

# Dashboard Security (REQUIRED for LIVE mode)
DASHBOARD_API_KEY=your-secret-key-here

# Trading Mode
EXECUTION_MODE=paper  # or 'live'
ENABLE_MAINNET_TRADING=false  # ⚠️ Set true for REAL trading!

# Trading Pairs (edit as needed)
TRADING_PAIRS=BTC,ETH,SOL,BNB,ADA,DOGE,XRP,AVAX,LINK,SUI

# Risk Limits
MAX_DRAWDOWN_PCT=0.12  # 12% max drawdown
DAILY_NOTIONAL_LIMIT_USD=500
HARD_MAX_LEVERAGE=7

# Risk:Reward
DEFAULT_SL_PCT=0.03    # 3% Stop Loss
DEFAULT_TP_PCT=0.05    # 5% Take Profit
```

**Security Notes:**
- Never commit `.env` (in `.gitignore`)
- Use `scripts/test_connection.py` to validate wallet/key match
- LIVE mode requires `DASHBOARD_API_KEY`

### Step 3: Test Connection
```bash
python scripts/test_connection.py
```
Fix any ❌ failures before proceeding.

### Step 4: Test Single Cycle
```bash
# Paper mode (safe)
python hyperliquid_bot_executable_orders.py --single-cycle

# Live mode simulation (no real orders)
EXECUTION_MODE=live ENABLE_MAINNET_TRADING=false python hyperliquid_bot_executable_orders.py --single-cycle
```

### Step 5: Production Run
```bash
# Terminal 1: Bot (detached recommended)
nohup python hyperliquid_bot_executable_orders.py > bot.log 2>&1 &

# Terminal 2: API Server
python api_server.py

# Terminal 3: Dashboard
cd frontend && npm run dev
```

**Dashboard:** [http://localhost:3000](http://localhost:3000)

## 📊 Dashboard Walkthrough

| Section | Description |
|---------|-------------|
| **Header** | Bot status, current analysis coin, mode (paper/live) |
| **Stats** | Balance, PnL, margin, trades, win rate, cycle time |
| **Drawdown** | Real-time drawdown bar (stops trading at 12%) |
| **TradingView** | Live candlesticks + order book (Lightweight Charts) |
| **Equity** | Real portfolio equity curve (no paper simulation) |
| **Positions** | Open positions with leverage, PnL |
| **Risk Mgmt** | Managed SL/TP/Trailing/Break-Even status |
| **Trades** | History + AI reasoning + CSV export |
| **Circuit Breakers** | API failure protection |
| **Logs** | Real-time filtered logs |

## 🔧 Configuration Reference (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `EXECUTION_MODE` | `paper` | `paper` (simulated) or `live` (real orders) |
| `ENABLE_MAINNET_TRADING` | `false` | `true` = REAL money (⚠️) |
| `TRADING_PAIRS` | `BTC,ETH,SOL,...` | Comma-separated list |
| `MAX_DRAWDOWN_PCT` | `0.12` | Stops trading at 12% drawdown |
| `DAILY_NOTIONAL_LIMIT_USD` | `500` | Max daily trade volume |
| `HARD_MAX_LEVERAGE` | `7` | Max leverage per position |
| `DEFAULT_SL_PCT` | `0.03` | 3% Stop Loss |
| `DEFAULT_TP_PCT` | `0.05` | 5% Take Profit |
| `DEFAULT_CYCLE_SEC` | `120` | Cycle interval (adaptive 30-300s) |

**Full list:** See `.env.example`

## 🛡️ Safety Features

- **Paper Mode**: Simulated orders (default)
- **Drawdown Protection**: Halts at 12% portfolio drawdown
- **Circuit Breakers**: API failures → fail-fast
- **Correlation Checks**: Blocks highly correlated positions
- **Emergency De-Risk**: Closes worst position at 85% margin
- **Daily Limits**: Notional caps per day
- **Trade Cooldown**: 5min between same-coin trades
- **Fill Verification**: Confirms orders actually filled
- **Graceful Shutdown**: SIGINT/SIGTERM saves state

## 📱 Telegram Alerts
Enable with `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`:
- Trade executions
- SL/TP/Trailing triggers
- Emergency closes
- Daily summaries
- Errors

## 🧪 Useful Scripts

```bash
# Full test
python scripts/test_connection.py

# Close SOL position (emergency)
python close_sol_position.py

# Minimal order test
python hyperliquid_minimal_order.py

# Check current positions
python check_current_positions.py
```

## 🚀 Docker (Optional)
```bash
docker-compose up  # See docker-compose.yml
```

## 🔍 Monitoring
- **Prometheus**: `/metrics` endpoint
- **Logs**: `logs/hyperliquid_bot.log` (JSON structured)
- **State**: `state/bot_state.json` (atomic writes)

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Dashboard blank** | Start `api_server.py` |
| **"API Server Not Running"** | `python api_server.py` |
| **Wallet mismatch** | Run `scripts/test_connection.py` |
| **No trades** | Check logs, ensure `EXECUTION_MODE=live` + `ENABLE_MAINNET_TRADING=true` |
| **LLM errors** | Verify `OPENROUTER_API_KEY` + credits |
| **Permission denied** | `chmod 700 state/ logs/` |
| **High latency** | Increase `DEFAULT_CYCLE_SEC` |

## 🏗️ Architecture

```
Bot (Python) ← CycleOrchestrator → LLM → RiskManager → ExchangeClient (EIP-712)
                    ↓
              StateStore (atomic JSON) → API Server (Flask) → React Dashboard
```

**Core Libraries:**
- `requests` + `eth_account` (Hyperliquid)
- `decimal.Decimal` (precision)
- `flask` + `react` (dashboard)
- `lightweight-charts` (candlesticks)

## 📄 License
MIT — Free for personal/commercial use.

## 🙌 Support
- [Discord](https://discord.gg/hyperliquid-bot)
- Issues: GitHub Discussions

**Happy Trading! 🚀**