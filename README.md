# Hyperliquid AI Trading Bot - Enterprise Edition

## 🎯 Overview

This is an **enterprise-grade, production-ready** autonomous trading bot that operates on Hyperliquid using AI (DeepSeek) to generate executable trading orders. The bot features comprehensive risk management, persistent state, structured observability, and robust error handling designed for 24/7 operation.

## ✨ Key Features

### ✅ Enterprise Features
- **Decimal-Only Precision**: All financial calculations use `Decimal` to avoid floating-point errors
- **Persistent State**: Automatic state/metrics persistence across restarts
- **Startup Health Checks**: Validates connectivity, wallet balance, disk space, and permissions
- **Circuit Breakers**: Protects against cascading failures from external API issues
- **Retry Logic**: Exponential backoff with jitter for transient failures
- **Structured Logging**: JSON-formatted logs for easy ingestion by log aggregators
- **Metrics Collection**: Prometheus-compatible metrics for monitoring
- **Health Monitoring**: Multi-check health system with file/API/disk checks
- **Graceful Shutdown**: Handles SIGTERM/SIGINT for clean process termination
- **Input Validation**: Comprehensive validation of all external inputs
- **Deterministic Fallback**: Safe de-risk or hold behavior when AI is unavailable
- **Live/Paper Parity**: Identical logic paths with simulated execution in paper mode

### 🛡️ Risk Management
- Per-symbol trade cooldown (configurable)
- Daily notional turnover caps
- Maximum margin usage limits
- Position size limits relative to balance
- Confidence thresholds for open/management actions
- Emergency stop on drawdown breaches
- Emergency stop on consecutive cycle failures

### 📊 Observability
- **Logs**: Structured JSON logs with timestamps, levels, and context
- **Metrics**: Counters, gauges, and histograms for all key operations
- **Health**: Real-time health status with detailed check results
- **Snapshots**: Periodic health snapshots with portfolio state and cycle results

## 📁 Project Structure

```
hyperliquid/
├── hyperliquid_bot_executable_orders.py  # Main bot orchestrator
├── exchange_client.py                   # Hyperliquid API client with signing
├── execution_engine.py                  # Action → execution mapping
├── llm_engine.py                        # DeepSeek integration with fallback
├── risk_manager.py                      # Risk checks and limits
├── state_store.py                       # Persistent state/metrics storage
├── technical_analyzer_simple.py         # Market data & technical indicators
├── models.py                            # Data models (MarketData, PortfolioState, TradingAction)
├── check_current_positions.py           # Utility: check positions
├── hyperliquid_minimal_order.py         # Utility: test minimal order
├── close_sol_position.py                # Utility: close specific position
├── utils/                               # Shared utilities
│   ├── __init__.py
│   ├── decimals.py                     # Decimal conversion & math helpers
│   ├── retry.py                        # Retry logic with exponential backoff
│   ├── circuit_breaker.py              # Circuit breaker pattern
│   ├── validation.py                   # Input validation
│   ├── logging_config.py               # Structured logging setup
│   ├── metrics.py                      # Metrics collection (Prometheus format)
│   └── health.py                       # Health check framework
├── logs/                               # Log files (auto-created)
│   ├── hyperliquid_bot_executable.log
│   ├── agent_health.json
│   ├── agent_state.json
│   └── agent_metrics.json
├── .env                                # Environment variables (create from .env.example)
├── .env.example                        # Example configuration
├── requirements.txt                    # Python dependencies
└── README.md                           # This file
```

## 🔧 Setup

### 1. Prerequisites
- Python 3.10+
- Git (optional)
- Virtual environment tool (venv, conda, etc.)

### 2. Installation
```bash
# Clone or extract the bot files
cd hyperliquid-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the project root:

```dotenv
# Required: Hyperliquid wallet credentials
HYPERLIQUID_WALLET_ADDRESS=0xYourWalletAddress
HYPERLIQUID_PRIVATE_KEY=0xYourPrivateKey

# Optional: DeepSeek API for AI-generated orders (if ALLOW_EXTERNAL_LLM=true)
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# Execution mode: "paper" (simulated) or "live" (real trading)
EXECUTION_MODE=paper

# Enable live trading (only after thorough testing!)
ENABLE_MAINNET_TRADING=false

# Use external LLM (DeepSeek) or deterministic fallback
ALLOW_EXTERNAL_LLM=false

# Include portfolio context in LLM prompt (requires ALLOW_EXTERNAL_LLM=true)
LLM_INCLUDE_PORTFOLIO_CONTEXT=false

# Risk limits
MAX_ORDER_MARGIN_PCT=0.10          # Max 10% of equity per order
HARD_MAX_LEVERAGE=10               # Maximum leverage allowed
MIN_CONFIDENCE_OPEN=0.20           # Min confidence to open position
MIN_CONFIDENCE_MANAGE=0.10         # Min confidence to manage position
MAX_DRAWDOWN_PCT=0.20              # Emergency stop at 20% drawdown
TRADE_COOLDOWN_SEC=300             # 5 minutes between trades on same symbol
DAILY_NOTIONAL_LIMIT_USD=5000     # Max daily turnover in USD
MAX_TRADES_PER_CYCLE=2             # Max orders per cycle
MAX_CONSECUTIVE_FAILED_CYCLES=3    # Emergency stop after N failed cycles

# Operational parameters
CYCLE_INTERVAL_SEC=300             # Time between cycles (5 minutes)
META_CACHE_TTL_SEC=60              # Cache metadata for 60 seconds
MAX_MARKET_DATA_AGE_SEC=120        # Max age of market data in seconds
PAPER_SLIPPAGE_BPS=3               # Simulated slippage in paper mode (3 bps)
SAFE_FALLBACK_MODE=de_risk         # "de_risk" (close positions) or "hold"

# Logging & monitoring
LOG_LEVEL=INFO                     # DEBUG, INFO, WARNING, ERROR
LOG_JSON_FORMAT=true               # Use JSON log format
LOG_FILE=logs/hyperliquid_bot_executable.log
HEALTH_FILE_PATH=logs/agent_health.json
STATE_FILE_PATH=logs/agent_state.json
METRICS_FILE_PATH=logs/agent_metrics.json
```

### 4. Validate Configuration
```bash
python hyperliquid_bot_executable_orders.py --config-test
```
This will check all environment variables and exit with status 0 if valid.

## 🚀 Running the Bot

### Single Cycle (Testing)
Run one trading cycle and exit:
```bash
python hyperliquid_bot_executable_orders.py --single-cycle
```

### Continuous Operation
Start the autonomous loop:
```bash
python hyperliquid_bot_executable_orders.py
```

### As a Service (systemd)
Create `/etc/systemd/system/hyperliquid-bot.service`:

```ini
[Unit]
Description=Hyperliquid Trading Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/hyperliquid-bot
Environment="PATH=/path/to/hyperliquid-bot/venv/bin"
EnvironmentFile=/path/to/hyperliquid-bot/.env
ExecStart=/path/to/hyperliquid-bot/venv/bin/python hyperliquid_bot_executable_orders.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable hyperliquid-bot
sudo systemctl start hyperliquid-bot
sudo systemctl status hyperliquid-bot
```

### Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "hyperliquid_bot_executable_orders.py"]
```

Build and run:
```bash
docker build -t hyperliquid-bot .
docker run -d --name hyperliquid-bot --env-file .env hyperliquid-bot
```

## 📊 Monitoring

### Logs
- **File**: `logs/hyperliquid_bot_executable.log` (JSON format if enabled)
- **Console**: stdout/stderr (captured by systemd/docker)
- **Log rotation**: Configure via logrotate or Docker logging driver

### Health Status
- **File**: `logs/agent_health.json` (updated each cycle)
- **Fields**: overall status, individual check results, portfolio snapshot

### Metrics
- **File**: `logs/agent_metrics.json` (cumulative counters and gauges)
- **Prometheus Export**: Use a sidecar or script to convert JSON to Prometheus format:
  ```bash
  python -c "from utils.metrics import MetricsCollector; import json; m=MetricsCollector(); m._metrics = json.load(open('logs/agent_metrics.json')); print(m.to_prometheus_format())"
  ```
- **Grafana Dashboard**: Import metrics as counters/gauges for visualization

### Key Metrics to Watch
- `cycles_total`, `cycles_failed` – overall health
- `trades_executed_total` – activity level
- `risk_rejections_total`, `execution_failures_total` – error rates
- `current_balance`, `peak_portfolio_value` – PnL tracking
- `consecutive_failed_cycles` – rising issues
- `cycle_duration_seconds` – performance

### Alerting Suggestions
- **Critical**: `is_emergency_stopped=true` in health file
- **Warning**: `consecutive_failed_cycles >= 2`
- **Warning**: `risk_rejections_total` increasing rapidly
- **Warning**: `current_balance` dropping below threshold
- **Info**: Any `UNHEALTHY` health check

## 🛑 Emergency Procedures

### Immediate Stop
```bash
# Systemd
sudo systemctl stop hyperliquid-bot

# Docker
docker stop hyperliquid-bot

# Direct process
pkill -f hyperliquid_bot_executable_orders.py
```

### Reset Emergency State
If the bot stopped due to emergency (drawdown, failures), edit `logs/agent_state.json`:
```json
{
  "consecutive_failed_cycles": 0,
  "is_emergency_stopped": false  // If present in health snapshot
}
```
Then restart the bot.

### Force Close Positions
Use the utility script:
```bash
python check_current_positions.py  # See current positions
# If you need to close a specific position:
python close_sol_position.py  # Example for SOL
```

## 🔍 Troubleshooting

### Bot Won't Start
1. Check `.env` variables are set and correct
2. Run `--config-test` to validate configuration
3. Check logs for specific error messages
4. Verify wallet address matches private key
5. Ensure `logs/` directory is writable

### No Trades Executing
1. Check `ALLOW_EXTERNAL_LLM` – if `false`, bot only uses fallback (hold/de-risk)
2. Check `MIN_CONFIDENCE_OPEN` – may be too high
3. Review health snapshot for risk rejections
4. Check market data freshness (Binance API reachable)
5. Verify `EXECUTION_MODE=paper` for testing

### High Rejection Rate
1. Review `risk_rejections_total` in metrics
2. Check individual `failed_checks` in health snapshot
3. Adjust risk parameters: increase `MAX_ORDER_MARGIN_PCT`, `DAILY_NOTIONAL_LIMIT_USD`, or decrease `MIN_CONFIDENCE_OPEN`
4. Check cooldown: `last_trade_timestamp_by_coin` in state file

### API Errors
1. Check circuit breaker status in health snapshot
2. Verify Hyperliquid API reachability
3. Check rate limits (not currently enforced, but consider adding)
4. Review network connectivity

### Stale Market Data
1. Check Binance API connectivity
2. Verify `MAX_MARKET_DATA_AGE_SEC` is reasonable (default 120s)
3. Check for network issues or Binance rate limiting

### Drawdown Emergency Stop
1. Bot automatically stops if drawdown exceeds `MAX_DRAWDOWN_PCT`
2. Review positions and market conditions
3. After addressing issue, reset `consecutive_failed_cycles` and `is_emergency_stopped` in state files
4. Consider reducing position sizes or leverage

## 🔐 Security Best Practices

1. **Never commit `.env`** – it contains private keys
2. **Use runtime secrets** in production (K8s secrets, Docker secrets, vault)
3. **Restrict file permissions** on `.env` (chmod 600)
4. **Rotate API keys** periodically
5. **Use separate wallets** for testing vs production
6. **Enable 2FA** on exchange accounts where possible
7. **Monitor logs** for unauthorized access attempts
8. **Run in isolated network** if possible (VPC, private subnet)

## 📈 Performance Tuning

### Cycle Interval
- Default: 300 seconds (5 minutes)
- Shorter: more responsive but higher API load
- Longer: less load but slower reaction

### Cache TTLs
- `META_CACHE_TTL_SEC`: 60s default – adjust based on how often asset IDs/leverage change
- Lower = more API calls, higher = stale metadata risk

### Concurrency
- Currently single-threaded per bot instance
- For higher throughput, run multiple bot instances with different wallets/pairs

## 🧪 Testing Strategy

1. **Paper Mode**: Run with `EXECUTION_MODE=paper` and `ENABLE_MAINNET_TRADING=false` for weeks
2. **Single Cycle**: Use `--single-cycle` to debug specific scenarios
3. **Fallback Mode**: Set `ALLOW_EXTERNAL_LLM=false` to test deterministic behavior
4. **Stress Test**: Lower `MIN_CONFIDENCE_OPEN` to generate more trades
5. **Failure Injection**: Simulate API failures to test retry/circuit breaker

## 📝 License
Internal use only. Not for redistribution without permission.

---

**Status**: ✅ Production Ready  
**Last Updated**: 2025-10-25  
**Maintainer**: AI Assistant (Dyad)