# Hyperliquid Trading Bot

An automated cryptocurrency trading bot for the Hyperliquid exchange, powered by AI (Claude via OpenRouter) for intelligent trading decisions. The bot analyzes real-time market data, manages risk, and executes trades with configurable parameters.

## 🚀 Features

### ✅ Core Functionality
- **AI-Powered Trading Decisions**: Uses Claude 3.5 Sonnet via OpenRouter for market analysis and trade recommendations
- **Real-Time Market Data**: Fetches live data from Binance API for technical indicators (EMA, MACD, RSI, ATR)
- **Risk Management**: Advanced risk controls including volatility-adjusted sizing, margin limits, and trade cooldowns
- **Hyperliquid Integration**: Direct API integration with EIP-712 signing for secure order execution
- **Portfolio Monitoring**: Real-time tracking of balances, positions, and PnL
- **Paper Trading Mode**: Safe testing environment with simulated executions
- **Circuit Breakers**: Automatic failure handling for API endpoints
- **Comprehensive Logging**: JSON-structured logs for monitoring and debugging

### 📊 Supported Assets
- **BTC**: Minimum 0.001 BTC (~$111)
- **ETH**: Minimum 0.001 ETH (~$4)
- **SOL**: Minimum 0.1 SOL (~$19)
- **BNB**: Minimum 0.001 BNB (~$1)
- **ADA**: Minimum 16.0 ADA (~$10.50)

### 🛡️ Safety Features
- **Fail-Safe Fallback**: Automatic hold/de-risk when AI is unavailable
- **Margin Protection**: Configurable limits on margin usage and per-trade exposure
- **Order Validation**: Pre-execution checks for price deviations and minimum sizes
- **Circuit Breakers**: Prevents cascading failures from API outages
- **Paper Mode**: Test strategies without real money

## 📋 Requirements

- Python 3.10+
- Valid Hyperliquid wallet with private key
- OpenRouter API key for Claude access
- Internet connection for API calls

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
# Required
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
HYPERLIQUID_WALLET_ADDRESS=your_wallet_address_here
DEEPSEEK_API_KEY=your_openrouter_api_key_here

# Execution Mode
EXECUTION_MODE=paper  # 'paper' for testing, 'live' for real trading
ENABLE_MAINNET_TRADING=false  # Set to 'true' only for live trading

# AI Settings
ALLOW_EXTERNAL_LLM=true  # Enable/disable AI trading decisions
LLM_INCLUDE_PORTFOLIO_CONTEXT=true  # Include portfolio data in AI prompts

# Risk Management
MAX_ORDER_MARGIN_PCT=0.1  # Max margin per trade (10%)
HARD_MAX_LEVERAGE=10  # Maximum leverage allowed
MIN_CONFIDENCE_OPEN=0.7  # Minimum confidence for opening positions
MIN_CONFIDENCE_MANAGE=0.5  # Minimum confidence for managing positions
MAX_MARGIN_USAGE=0.8  # Maximum total margin usage (80%)
TRADE_COOLDOWN_SEC=300  # Minimum seconds between trades per coin
DAILY_NOTIONAL_LIMIT_USD=1000  # Daily trading limit

# Performance
MAX_TRADES_PER_CYCLE=5  # Maximum trades per cycle
MAX_CONSECUTIVE_FAILED_CYCLES=10  # Shutdown after this many failures
META_CACHE_TTL_SEC=300  # Cache TTL for exchange metadata
MAX_MARKET_DATA_AGE_SEC=300  # Maximum age for market data
PAPER_SLIPPAGE_BPS=50  # Simulated slippage in paper mode
```

### Trading Pairs and Minimums

The bot trades the following pairs with these minimum sizes:
- BTC: 0.001
- ETH: 0.001  
- SOL: 0.1
- BNB: 0.001
- ADA: 16.0

## 🚀 Usage

### Testing (Paper Mode)

1. Set `EXECUTION_MODE=paper` in `.env`
2. Run a single test cycle:
   ```bash
   python hyperliquid_bot_executable_orders.py --single-cycle
   ```

3. Monitor logs in `logs/hyperliquid_bot.log`

### Live Trading

⚠️ **WARNING**: Live trading involves real money. Test thoroughly in paper mode first!

1. Set `EXECUTION_MODE=live` and `ENABLE_MAINNET_TRADING=true` in `.env`
2. Start the bot:
   ```bash
   python hyperliquid_bot_executable_orders.py
   ```

### Utility Scripts

- **Check Positions**: `python check_current_positions.py`
- **Close SOL Position**: `python close_sol_position.py`
- **Test Minimal Order**: `python hyperliquid_minimal_order.py`

## 📊 Monitoring

### Logs
- Main log: `logs/hyperliquid_bot.log` (JSON format)
- State files: `state/bot_state.json`, `state/bot_metrics.json`

### Key Metrics
- Cycle duration and success rate
- Trades executed vs. risk rejections
- Portfolio value and margin usage
- API error rates

### Health Checks
The bot includes circuit breakers for:
- Hyperliquid `/info` endpoint
- Hyperliquid `/exchange` endpoint
- OpenRouter API

## 🔧 Troubleshooting

### No Trades Executing

1. **Check LLM Settings**:
   - Verify `ALLOW_EXTERNAL_LLM=true`
   - Ensure `DEEPSEEK_API_KEY` is valid
   - Check OpenRouter API quota/limits

2. **Review Confidence Thresholds**:
   - `MIN_CONFIDENCE_OPEN` may be too high (default 0.7)
   - `MIN_CONFIDENCE_MANAGE` for position management

3. **Check Risk Rejections**:
   - Review logs for risk rejection reasons
   - Verify margin usage isn't exceeding `MAX_MARGIN_USAGE`
   - Check trade cooldowns (`TRADE_COOLDOWN_SEC`)

4. **Market Data Issues**:
   - Ensure Binance API is reachable
   - Check `MAX_MARKET_DATA_AGE_SEC` for stale data

5. **Execution Mode**:
   - Confirm `EXECUTION_MODE=paper` for testing
   - For live: `EXECUTION_MODE=live` and `ENABLE_MAINNET_TRADING=true`

### Common Issues

- **"Circuit breaker OPEN"**: API endpoint is failing, check network and API status
- **"Order price cannot be more than 95% away from reference price"**: Price validation failed, check reference price logic
- **"User or API Wallet does not exist"**: Invalid wallet address or private key
- **LLM API errors**: Check OpenRouter key and quota

### Recovery Steps

1. **Restart in Paper Mode**: Switch to paper trading to test
2. **Check Balances**: Use `check_current_positions.py`
3. **Manual Intervention**: Close positions with utility scripts if needed
4. **Log Analysis**: Review JSON logs for detailed error information

## 🛡️ Security

- **Private Keys**: Never commit `.env` file or expose private keys
- **API Keys**: Rotate OpenRouter keys regularly
- **Network**: Use HTTPS for all API calls
- **Validation**: All orders validated before execution
- **Fallback**: Safe fallback to hold when systems fail

## 📈 Performance

- **Cycle Time**: ~30-45 seconds per trading cycle
- **API Calls**: Optimized with caching and circuit breakers
- **Memory**: Lightweight, no heavy ML libraries
- **Precision**: Decimal arithmetic for all financial calculations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Test changes in paper mode
4. Submit a pull request

## 📄 License

This project is for educational and personal use. Trading cryptocurrencies involves significant risk. Use at your own discretion.

## ⚠️ Disclaimer

This software is provided as-is without warranty. Cryptocurrency trading is highly risky and can result in total loss of funds. Always test strategies thoroughly and never risk more than you can afford to lose. The authors are not responsible for any financial losses incurred through use of this software.