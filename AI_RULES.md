# AI Rules for Hyperliquid Trading Bot

## Tech Stack
- **Python 3.10+**: Core language for the bot, leveraging type hints (`typing`), dataclasses, and enums for structured code.
- **requests**: Primary HTTP client for all API interactions (Hyperliquid, OpenRouter).
- **eth_account**: Handles EIP-712 signing for Hyperliquid orders using `Account.from_key()` and `encode_typed_data`.
- **pycryptodome (Crypto.Hash.keccak)**: Keccak-256 hashing for Hyperliquid action signatures.
- **msgpack**: Binary serialization for Hyperliquid payloads (`msgpack.packb`).
- **decimal.Decimal**: Precise arithmetic for all financial calculations (prices, sizes, margins, PnL).
- **python-dotenv**: Environment variable loading for secrets (private keys, API keys).
- **logging**: Built-in module for structured JSON logging to files and console.

## LLM Configuration
- **Model**: `anthropic/claude-opus-4.6` via OpenRouter (`https://openrouter.ai/api/v1`)
- **API Key**: `OPENROUTER_API_KEY` environment variable
- **Timeout**: 90 seconds (Claude Opus 4.6 can take longer than smaller models)
- **Retries**: 2 retries on 429/500/502/503/504 with exponential backoff
- **Temperature**: 0.2 (low for deterministic trading decisions)

## Data Sources
- **ALL market data comes from Hyperliquid API exclusively**
- No Binance, CoinGecko, or other external data sources
- Candle snapshots, mid prices, funding rates, open interest — all from Hyperliquid `/info`
- Technical indicators (EMA, MACD, RSI, ATR, Bollinger Bands) calculated from Hyperliquid candles

## Library Usage Rules
Follow these rules strictly to avoid precision errors, API incompatibilities, and security issues:

### HTTP & API Clients
- **Use `requests` exclusively** for all synchronous HTTP calls (Hyperliquid `/info`, `/exchange`, OpenRouter completions). Never use `urllib`, `aiohttp`, or `httpx`.
- Set `timeout=15-90s` on all requests. Always use `json=payload` for POST and handle `response.json()` with status checks.
- For Hyperliquid: Use `Content-Type: application/json` headers only; sign payloads with EIP-712 via `eth_account`.

### Crypto & Signing
- **EIP-712 signing: `eth_account` only**. Use `Account.from_key(private_key)` and `sign_l1_action_exact` pattern from `exchange_client.py`. Never implement manual signing.
- **Hashing: `Crypto.Hash.keccak` exclusively** for action hashes. Import as `from Crypto.Hash import keccak`.
- **Msgpack: Use `msgpack.packb`** for Hyperliquid action data before hashing. Never use JSON for signed payloads.

### Financial Precision
- **All money/math: `decimal.Decimal(str(value))`**. Convert floats/JSON to Decimal immediately. Never use `float` for prices, sizes, margins, or PnL.
- Round prices to tick sizes dynamically via `get_tick_size_and_precision`. Use `max_leverage` from `/meta` API.

### Configuration & Secrets
- **Env vars: `dotenv.load_dotenv()` at module top**. Access via `os.getenv('KEY')`. Document in `.env.example`.
- Update `requirements.txt` for any new libs.

### Data & Logging
- **Structured data: `dataclass` and `Dict[str, Any]`**. Use `Enum` for actions (e.g., `TradingAction`).
- **Logging: structured JSON format** with file+console handlers. Use `logger.info/error` at INFO level. No `print` for production logic.
- **JSON parsing: `json.loads` with regex extraction if LLM responses are messy**. Validate schemas before execution.

### State Management
- **Atomic writes**: State files use write-to-temp-then-rename pattern to prevent corruption.
- **Daily notional tracking**: Uses per-day keys with automatic 7-day cleanup.
- **Graceful shutdown**: Signal handlers (SIGINT/SIGTERM) save state before exit.

### Circuit Breakers
- **OPEN -> HALF_OPEN transition**: Based on `recovery_timeout` elapsed time.
- **HALF_OPEN -> CLOSED**: On first successful call.
- **HALF_OPEN -> OPEN**: On failure during half-open.

### Prohibitions
- No async code (`asyncio`, `aiohttp`) unless explicitly requested.
- No new ML/data libs (e.g., pandas, numpy) – keep lightweight.
- No float in trading logic – causes Hyperliquid rejections.
- No external data sources (Binance, CoinGecko, etc.) – Hyperliquid only.
- Test all changes with `--single-cycle` before continuous runs.

**Enforced by AI Editor**: All future changes must follow these rules. Violations will be rejected.