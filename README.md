# Hyperliquid Trading Bot

An automated cryptocurrency trading bot for the Hyperliquid exchange, powered by **Claude Opus 4** via OpenRouter for intelligent trading decisions. All market data is sourced **exclusively from Hyperliquid API** — no external data providers.

## 🚀 Features

### ✅ Core Functionality
- **AI-Powered Trading**: Claude Opus 4 (`anthropic/claude-opus-4`) via OpenRouter analyzes market data and generates executable trading decisions
- **Hyperliquid-Only Data**: All market data (candles, mid prices, funding rates, open interest) sourced directly from Hyperliquid API
- **Technical Analysis**: EMA, MACD, RSI, ATR, Bollinger Bands calculated from Hyperliquid candle snapshots
- **Risk Management**: Volatility-adjusted sizing, margin limits, trade cooldowns, and daily notional caps
- **Secure Execution**: EIP-712 signed orders via `eth_account` for Hyperliquid mainnet
- **Paper Trading Mode**: Safe testing with simulated executions and slippage
- **Circuit Breakers**: Automatic failure handling for API endpoints
- **Robust Connections**: HTTP session pooling, automatic retries, and configurable timeouts
- **Structured Logging**: JSON-formatted logs for monitoring and debugging

### 📊 Supported Assets
| Asset | Minimum Size | Approx. Value |
|-------|-------------|---------------|
| BTC   | 0.001       | ~$111         |
| ETH   | 0.001       | ~$4           |
| SOL   | 0.1         | ~$19          |
| BNB   | 0.001       | ~$1           |
| ADA   | 16.0        | ~$10.50       |

### 🛡️ Safety Features
- **Fail-Safe Fallback**: Automatic hold/de-risk when AI is unavailable
- **Margin Protection**: Configurable limits on margin usage and per-trade exposure
- **Order Validation**: Pre-execution checks for price deviations and minimum sizes
- **Circuit Breakers**: Prevents cascading failures from API outages
- **Paper Mode**: Test strategies without real money
- **Startup Connectivity Check**: Verifies Hyperliquid API before starting

## 📋 Requirements

- Python 3.10+
- Valid Hyperliquid wallet with private key
- OpenRouter API key (for Claude Opus 4 access)
- Internet connection

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd hyperliquid-trading-bot
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# === REQUIRED ===
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# === Execution Mode ===
EXECUTION_MODE=paper              # 'paper' or 'live'
ENABLE_MAINNET_TRADING=false      # Set 'true' ONLY for live trading

# === AI / LLM Settings ===
ALLOW_EXTERNAL_LLM=true
LLM_INCLUDE_PORTFOLIO_CONTEXT=true
LLM_MODEL=anthropic/claude-opus-4
LLM_MAX_TOKENS=8192
LLM_TEMPERATURE=0.2

# === Risk Management ===
MAX_ORDER_MARGIN_PCT=0.1          # Max 10% of balance per trade
HARD_MAX_LEVERAGE=10              # Maximum leverage
MIN_CONFIDENCE_OPEN=0.7           # Min confidence to open positions
MIN_CONFIDENCE_MANAGE=0.5         # Min confidence to manage positions
MAX_MARGIN_USAGE=0.8              # Max 80% total margin usage
TRADE_COOLDOWN_SEC=300            # 5 min cooldown per coin
DAILY_NOTIONAL_LIMIT_USD=1000     # Daily trading limit

# === Performance ===
MAX_TRADES_PER_CYCLE=5
MAX_CONSECUTIVE_FAILED_CYCLES=10
META_CACHE_TTL_SEC=300
MAX_MARKET_DATA_AGE_SEC=300
PAPER_SLIPPAGE_BPS=50

# === Hyperliquid API ===
HYPERLIQUID_BASE_URL=https://api.hyperliquid.xyz
HYPERLIQUID_INFO_TIMEOUT=15
HYPERLIQUID_EXCHANGE_TIMEOUT=30

# === Safety ===
SAFE_FALLBACK_MODE=de_risk
AUTO_CONFIRM_MINIMAL_ORDER=false

# === Logging ===
LOG_LEVEL=INFO
LOG_FILE=logs/hyperliquid_bot.log
LOG_JSON_FORMAT=true
```

### How to Get API Keys

1. **Hyperliquid Wallet**:
   - Go to [hyperliquid.xyz](https://hyperliquid.xyz)
   - Connect or create a wallet
   - Export your private key (never share it!)

2. **OpenRouter API Key**:
   - Go to [openrouter.ai](https://openrouter.ai)
   - Sign up and create an API key
   - Add credits (~$0.01-0.05 per LLM call)
   - The bot uses `anthropic/claude-opus-4` model

## 🚀 Usage

### Testing (Paper Mode)

```bash
# Single cycle test
python hyperliquid_bot_executable_orders.py --single-cycle

# Continuous paper trading
python hyperliquid_bot_executable_orders.py
```

### Live Trading

⚠️ **WARNING**: Live trading involves real money. Test thoroughly first!

```bash
# Set in .env:
# EXECUTION_MODE=live
# ENABLE_MAINNET_TRADING=true

python hyperliquid_bot_executable_orders.py
```

### Utility Scripts

```bash
# Check positions and balances
python check_current_positions.py

# Test minimal order (with connectivity check)
python hyperliquid_minimal_order.py
```

## 🔄 How It Works

### Trading Cycle (every 60 seconds)

1. **Connect**: Verify Hyperliquid API connectivity
2. **Portfolio**: Fetch balances and positions from Hyperliquid
3. **Market Data**: Get candle snapshots, mid prices, and funding rates from Hyperliquid
4. **Technical Analysis**: Calculate EMA, MACD, RSI, ATR, Bollinger Bands from Hyperliquid candles
5. **AI Decision**: Send all data to Claude Opus 4 for analysis
6. **Risk Check**: Validate decision against risk parameters
7. **Execute**: Place order on Hyperliquid (or simulate in paper mode)
8. **Log**: Record results and update state

### Data Flow

```
Hyperliquid API ──→ Candle Snapshots ──→ Technical Indicators ──┐
                ──→ Mid Prices ─────────────────────────────────┤
                ──→ Funding Rates ──────────────────────────────┤
                ──→ Portfolio State ─────────────────────────────┤
                                                                 ▼
                                                    Claude Opus 4 (OpenRouter)
                                                                 │
                                                                 ▼
                                                    Trading Decision (JSON)
                                                                 │
                                                                 ▼
                                                    Risk Manager Validation
                                                                 │
                                                                 ▼
                                                    Execution on Hyperliquid
```

## 📊 Monitoring

### Logs
- Main log: `logs/hyperliquid_bot.log` (JSON format)
- State: `state/bot_state.json`
- Metrics: `state/bot_metrics.json`

### Key Metrics
- Cycle duration and success rate
- Trades executed vs. risk rejections
- LLM call count and error rate
- Portfolio value and margin usage

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| No trades executing | Check `OPENROUTER_API_KEY`, lower `MIN_CONFIDENCE_OPEN` |
| Circuit breaker OPEN | Check network, Hyperliquid API status |
| LLM errors | Verify OpenRouter key and credits |
| Order rejected | Check minimum sizes, price deviation limits |
| Stale data | Check `META_CACHE_TTL_SEC`, `MAX_MARKET_DATA_AGE_SEC` |

## 🛡️ Security

- Private keys stored only in `.env` (never committed)
- HTTPS for all API calls
- EIP-712 cryptographic signing for orders
- Circuit breakers prevent cascading failures
- Safe fallback to hold when systems fail

## ⚠️ Disclaimer

This software is provided as-is without warranty. Cryptocurrency trading is highly risky and can result in total loss of funds. Always test thoroughly in paper mode and never risk more than you can afford to lose.